"""Food logging pipeline: text -> estimated meal (stored) -> player adjusts -> confirmed.

Nutrition values come only from FoodData Central (cached in fdc_foods / fdc_food_portions).
Confirmed meals feed the HealthScore's nutrition category and award meal_logged points.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from supabase import Client

from app.food import lexicon, parser
from app.food.fdc import FdcClient, FdcError, Food, Portion, SearchHit, description_confidence, rank_hits
from app.food.portions import nutrients, to_grams, unit_options
from app.gamification import LEVEL_THRESHOLDS, POINTS, PointAction

CACHE_DAYS = 30
REVIEW_BELOW = 0.6          # match confidence under this asks the player to check the food
SEARCH_RESULTS = 10         # hits shown in the food picker
SEARCH_CACHED = 25          # hits kept per cached query, re-ranked on read
NUTRIENT_KEYS = ("calories", "protein_g", "carbs_g", "fat_g")


class MealError(Exception):
    """A request that can't be done in the meal's current state (mapped to 4xx)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class Resolution:
    food: Food | None
    confidence: float
    alternatives: list[dict] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh(fetched_at: str | None) -> bool:
    if not fetched_at:
        return False
    ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - ts < timedelta(days=CACHE_DAYS)


def _iso_date(text: str | None) -> str | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text or "", fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _hit_dict(h: SearchHit) -> dict:
    return {"fdc_id": h.fdc_id, "description": h.description, "data_type": h.data_type,
            "calories_per_100g": h.calories_per_100g, "rank_score": round(h.rank_score, 2)}


# --- FDC cache ---------------------------------------------------------------------

class Catalog:
    """FoodData Central with a Supabase cache in front of it."""

    def __init__(self, supabase: Client, fdc: FdcClient):
        self.db = supabase
        self.fdc = fdc
        self._foods: dict[int, Food] = {}

    def food(self, fdc_id: int) -> Food:
        if fdc_id in self._foods:
            return self._foods[fdc_id]
        rows = self.db.table("fdc_foods").select("*").eq("fdc_id", fdc_id).limit(1).execute().data
        if rows and _fresh(rows[0].get("fetched_at")):
            r = rows[0]
            portions = self.db.table("fdc_food_portions").select("*").eq("fdc_id", fdc_id).execute().data
            food = Food(
                fdc_id=r["fdc_id"], description=r["description"], data_type=r.get("data_type") or "",
                per_100g={"calories": r.get("calories_per_100g"), "protein_g": r.get("protein_g_per_100g"),
                          "carbs_g": r.get("carbs_g_per_100g"), "fat_g": r.get("fat_g_per_100g")},
                other_nutrients=r.get("other_nutrients") or {},
                portions=[Portion(p["label"], float(p["gram_weight"]), float(p.get("amount") or 1), p.get("fdc_portion_id"))
                          for p in portions],
            )
        else:
            food = self.fdc.food(fdc_id)
            self._store(food)
        self._foods[fdc_id] = food
        return food

    def _store(self, food: Food) -> None:
        self.db.table("fdc_foods").upsert({
            "fdc_id": food.fdc_id, "description": food.description, "data_type": food.data_type,
            "brand_owner": food.brand_owner, "gtin_upc": food.gtin_upc,
            "calories_per_100g": food.per_100g.get("calories"), "protein_g_per_100g": food.per_100g.get("protein_g"),
            "carbs_g_per_100g": food.per_100g.get("carbs_g"), "fat_g_per_100g": food.per_100g.get("fat_g"),
            "other_nutrients": food.other_nutrients, "publication_date": _iso_date(food.publication_date),
            "fetched_at": _now(),
        }, on_conflict="fdc_id").execute()
        self.db.table("fdc_food_portions").delete().eq("fdc_id", food.fdc_id).execute()
        if food.portions:
            self.db.table("fdc_food_portions").insert([
                {"fdc_id": food.fdc_id, "fdc_portion_id": p.fdc_portion_id, "label": p.label,
                 "amount": p.amount, "gram_weight": p.gram_weight}
                for p in food.portions
            ]).execute()

    def search(self, query: str) -> list[SearchHit]:
        key = lexicon.normalize(query)
        rows = self.db.table("fdc_search_cache").select("*").eq("query", key).limit(1).execute().data
        if rows and _fresh(rows[0].get("fetched_at")):
            # re-ranked on read so ranking improvements apply to cached queries too
            cached = [SearchHit(r["fdc_id"], r["description"], r["data_type"], r["calories_per_100g"], 0.0, r["rank_score"])
                      for r in rows[0]["results"]]
            return rank_hits(key, cached)[:SEARCH_RESULTS]
        hits = self.fdc.search_ranked(key)[:SEARCH_CACHED]
        self.db.table("fdc_search_cache").upsert(
            {"query": key, "results": [_hit_dict(h) for h in hits], "fetched_at": _now()}, on_conflict="query"
        ).execute()
        return hits[:SEARCH_RESULTS]

    def resolve(self, item: parser.ParsedItem) -> Resolution:
        """Known foods use their pinned FDC id; anything else is searched."""
        if item.food_name:
            return Resolution(self.food(lexicon.foods()[item.food_name].fdc_id), 1.0)
        hits = self.search(item.text)
        alts = [_hit_dict(h) for h in hits[:5]]
        conf = description_confidence(item.text, hits[0].description) if hits else 0.0
        if hits and (conf >= REVIEW_BELOW or not item.fallback_food):
            # If FDC can't return the top match, try the next ones before giving up.
            for hit in hits[:3]:
                try:
                    food = self.food(hit.fdc_id)
                except FdcError:
                    continue
                return Resolution(food, description_confidence(item.text, hit.description), alts)
        if item.fallback_food:
            known = lexicon.foods()[item.fallback_food]
            return Resolution(self.food(known.fdc_id), 0.5, alts)
        return Resolution(None, 0.0, alts)


# --- meals -------------------------------------------------------------------------

def _item_row(meal_id: str, text: str, quantity: float | None, unit: str | None, res: Resolution,
              is_assumed: bool = False, source_dish: str | None = None) -> dict:
    row = {
        "meal_id": meal_id, "ingredient_text": text, "quantity": quantity if quantity else 1,
        "unit": unit, "is_assumed": is_assumed, "source_dish": source_dish,
        "match_confidence": round(res.confidence, 2), "alternatives": res.alternatives,
        "fdc_id": res.food.fdc_id if res.food else None,
    }
    if res.food is None:
        return {**row, "grams": None, "portion_label": "No matching food found - pick one",
                "needs_review": True, **{k: None for k in NUTRIENT_KEYS}}
    g = to_grams(quantity, unit, res.food, text)
    return {**row, "grams": round(g.grams, 1), "portion_label": g.label,
            "needs_review": g.needs_review or res.confidence < REVIEW_BELOW,
            **nutrients(res.food, g.grams)}


def _recalculate_totals(db: Client, meal_id: str) -> None:
    items = db.table("meal_items").select("calories, protein_g, carbs_g, fat_g").eq("meal_id", meal_id).execute().data
    totals = {k: round(sum(float(i[k] or 0) for i in items), 1) for k in NUTRIENT_KEYS}
    db.table("meal_entries").update(totals).eq("meal_id", meal_id).execute()


def _meal_row(db: Client, meal_id: str) -> dict:
    rows = db.table("meal_entries").select("*").eq("meal_id", meal_id).limit(1).execute().data
    if not rows:
        raise MealError(404, "Meal not found")
    return rows[0]


def _editable(db: Client, meal_id: str) -> dict:
    meal = _meal_row(db, meal_id)
    if meal["status"] != "estimated":
        raise MealError(409, f"This meal is already {meal['status']}")
    return meal


def load_meal(db: Client, catalog: Catalog, meal_id: str) -> dict:
    meal = _meal_row(db, meal_id)
    items = db.table("meal_items").select("*").eq("meal_id", meal_id).order("created_at").execute().data
    out_items = []
    for it in items:
        food = catalog.food(it["fdc_id"]) if it.get("fdc_id") else None
        out_items.append({
            **it,
            "food": {"fdc_id": food.fdc_id, "description": food.description} if food else None,
            "unit_options": unit_options(food) if food else [],
        })
    return {**meal, "items": out_items,
            "totals": {k: float(meal.get(k) or 0) for k in NUTRIENT_KEYS}}


def analyze(db: Client, catalog: Catalog, user_id: str, text: str, log_date: date, meal_type: str | None) -> dict:
    parsed = parser.parse(text)
    if not parsed.items:
        raise MealError(422, "Couldn't find any foods in that. Try something like '2 eggs and a slice of toast'.")
    meal = db.table("meal_entries").insert({
        "user_id": user_id, "log_date": log_date.isoformat(), "meal_type": meal_type or parsed.meal_type,
        "raw_text": text, "display_name": parsed.display_name, "status": "estimated",
    }).execute().data[0]
    rows = []
    for item in parsed.items:
        res = catalog.resolve(item)
        rows.append(_item_row(meal["meal_id"], item.text, item.quantity, item.unit, res, item.is_assumed, item.source_dish))
    db.table("meal_items").insert(rows).execute()
    _recalculate_totals(db, meal["meal_id"])
    return load_meal(db, catalog, meal["meal_id"])


def update_item(db: Client, catalog: Catalog, meal_id: str, item_id: str, quantity: float | None,
                unit: str | None, unit_given: bool, fdc_id: int | None) -> dict:
    _editable(db, meal_id)
    rows = db.table("meal_items").select("*").eq("meal_item_id", item_id).eq("meal_id", meal_id).limit(1).execute().data
    if not rows:
        raise MealError(404, "Ingredient not found")
    item = rows[0]
    if fdc_id is not None:
        res = Resolution(catalog.food(fdc_id), 1.0, item.get("alternatives") or [])   # the player picked it
    elif item.get("fdc_id"):
        res = Resolution(catalog.food(item["fdc_id"]), float(item.get("match_confidence") or 1.0), item.get("alternatives") or [])
    else:
        raise MealError(422, "Pick a food for this ingredient first")
    new_unit = (None if unit == "count" else unit) if unit_given else item.get("unit")
    new_qty = quantity if quantity is not None else float(item["quantity"])
    # Editing an ingredient makes it the player's own (no longer "assumed"); picking a food
    # (even the same one, via "looks right") clears the low-confidence flag.
    row = _item_row(meal_id, item["ingredient_text"], new_qty, new_unit, res, False, item.get("source_dish"))
    row.pop("meal_id")
    db.table("meal_items").update(row).eq("meal_item_id", item_id).execute()
    _recalculate_totals(db, meal_id)
    return load_meal(db, catalog, meal_id)


def add_item(db: Client, catalog: Catalog, meal_id: str, text: str, quantity: float | None, unit: str | None) -> dict:
    _editable(db, meal_id)
    if quantity is None and unit is None:
        item = parser.parse_ingredient(text)        # "2 tbsp sour cream" typed in one box
    else:
        known = lexicon.find_food(text)
        item = parser.ParsedItem(text, quantity, None if unit == "count" else unit, known.name if known else None)
    db.table("meal_items").insert(_item_row(meal_id, item.text, item.quantity, item.unit, catalog.resolve(item))).execute()
    _recalculate_totals(db, meal_id)
    return load_meal(db, catalog, meal_id)


def delete_item(db: Client, catalog: Catalog, meal_id: str, item_id: str) -> dict:
    _editable(db, meal_id)
    db.table("meal_items").delete().eq("meal_item_id", item_id).eq("meal_id", meal_id).execute()
    _recalculate_totals(db, meal_id)
    return load_meal(db, catalog, meal_id)


def confirm(db: Client, catalog: Catalog, meal_id: str) -> dict:
    meal = _editable(db, meal_id)
    items = db.table("meal_items").select("ingredient_text, fdc_id").eq("meal_id", meal_id).execute().data
    if not items:
        raise MealError(422, "Add at least one ingredient before confirming")
    missing = [i["ingredient_text"] for i in items if not i.get("fdc_id")]
    if missing:
        raise MealError(422, f"Pick a food for: {', '.join(missing)}")
    db.table("meal_entries").update({"status": "confirmed", "confirmed_at": _now()}).eq("meal_id", meal_id).execute()
    db.rpc("award_points", {
        "p_user_id": meal["user_id"], "p_action": PointAction.meal_logged.value,
        "p_points": POINTS[PointAction.meal_logged], "p_level_thresholds": LEVEL_THRESHOLDS,
        "p_source_id": meal_id,
    }).execute()
    return load_meal(db, catalog, meal_id)


def discard(db: Client, catalog: Catalog, meal_id: str) -> dict:
    _editable(db, meal_id)
    db.table("meal_entries").update({"status": "discarded"}).eq("meal_id", meal_id).execute()
    return load_meal(db, catalog, meal_id)


def list_meals(db: Client, catalog: Catalog, user_id: str, log_date: date, status: str | None = None) -> list[dict]:
    query = db.table("meal_entries").select("meal_id").eq("user_id", user_id).eq("log_date", log_date.isoformat())
    if status:
        query = query.eq("status", status)
    rows = query.order("created_at").execute().data
    return [load_meal(db, catalog, r["meal_id"]) for r in rows]
