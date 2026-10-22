"""USDA FoodData Central client: search, food details, and ranking of search results.

Docs: https://fdc.nal.usda.gov/api-guide. The key comes from FDC_API_KEY (backend only).
"""

import os
import re
from dataclasses import dataclass, field

import httpx

BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# FNDDS ("as eaten") foods have consistent nutrients and household portions, including a
# default serving; SR Legacy and Foundation fill the gaps.
PREFERRED_TYPES = ["Survey (FNDDS)"]
FALLBACK_TYPES = ["SR Legacy", "Foundation"]

# FDC nutrient numbers
NUTRIENTS = {"208": "calories", "203": "protein_g", "205": "carbs_g", "204": "fat_g"}
EXTRA_NUTRIENTS = {"291": "fiber_g", "269": "sugars_g", "307": "sodium_mg", "601": "cholesterol_mg", "606": "saturated_fat_g"}


class FdcError(Exception):
    pass


@dataclass
class Portion:
    label: str              # "1 large", "1 tablespoon", "Quantity not specified"
    gram_weight: float
    amount: float = 1.0
    fdc_portion_id: int | None = None


@dataclass
class Food:
    fdc_id: int
    description: str
    data_type: str
    per_100g: dict           # calories, protein_g, carbs_g, fat_g
    other_nutrients: dict = field(default_factory=dict)
    portions: list[Portion] = field(default_factory=list)
    brand_owner: str | None = None
    gtin_upc: str | None = None
    publication_date: str | None = None


@dataclass
class SearchHit:
    fdc_id: int
    description: str
    data_type: str
    calories_per_100g: float | None
    fdc_score: float = 0.0
    rank_score: float = 0.0


def _nutrient_number(n: dict) -> str | None:
    return n.get("nutrientNumber") or (n.get("nutrient") or {}).get("number")


def _nutrient_value(n: dict) -> float | None:
    value = n.get("value", n.get("amount"))
    return float(value) if value is not None else None


def _portion_label(p: dict) -> str:
    """Normalise the three portion formats (FNDDS, SR Legacy, Foundation) into one label."""
    if p.get("portionDescription"):
        return p["portionDescription"].strip()
    amount = p.get("amount") or 1
    amount_text = f"{amount:g}"
    unit = ((p.get("measureUnit") or {}).get("name") or "").strip()
    modifier = (p.get("modifier") or "").strip()
    parts = [amount_text]
    if unit and unit.lower() not in ("undetermined", "racc"):
        parts.append(unit)
    if modifier and not modifier.isdigit():
        parts.append(modifier)
    if unit.lower() == "racc":
        parts.append("serving (RACC)")
    return " ".join(parts)


def parse_food(data: dict) -> Food:
    per_100g, other = {}, {}
    for n in data.get("foodNutrients", []):
        number, value = _nutrient_number(n), _nutrient_value(n)
        if value is None:
            continue
        if number in NUTRIENTS:
            per_100g[NUTRIENTS[number]] = value
        elif number in EXTRA_NUTRIENTS:
            other[EXTRA_NUTRIENTS[number]] = value
    portions = []
    for p in data.get("foodPortions", []):
        weight = p.get("gramWeight")
        if weight and weight > 0:
            # FNDDS portions describe one unit ("1 cup"); SR Legacy carries an amount.
            amount = 1.0 if p.get("portionDescription") else float(p.get("amount") or 1)
            portions.append(Portion(_portion_label(p), float(weight), amount, p.get("id")))
    return Food(
        fdc_id=data["fdcId"],
        description=data["description"],
        data_type=data.get("dataType", ""),
        per_100g=per_100g,
        other_nutrients=other,
        portions=portions,
        brand_owner=data.get("brandOwner"),
        gtin_upc=data.get("gtinUpc"),
        publication_date=data.get("publicationDate"),
    )


# --- ranking ---------------------------------------------------------------------

# Words that make a food more specific/processed. Penalised unless the query asks for them.
PROCESSED = {
    "powder", "dehydrated", "dried", "chips", "baked", "fried", "canned", "frozen", "juice", "nectar",
    "sauce", "soup", "flavored", "baby", "infant", "toddler", "sweetened", "imitation", "substitute",
    "reduced", "low", "free", "light", "lite", "diet", "concentrate", "pudding", "pie", "cake", "bread",
    "salad", "sandwich", "spread", "dip", "creamed", "candied", "mix", "formula", "smoothie",
    "white", "yolk", "glazed", "breaded", "stuffed", "with", "made", "cooked", "boiled", "roasted",
}
GENERIC = {"raw", "nfs", "whole", "plain", "regular", "fresh", "ns", "a", "or", "as", "to", "type", "made", "from"}


def _words(text: str) -> list[str]:
    return [w.rstrip("s") if len(w) > 3 else w for w in re.findall(r"[a-z]+", text.lower())]


def rank_score(query: str, description: str, data_type: str, fdc_score: float = 0.0) -> float:
    q = set(_words(query))
    desc_words = _words(description)
    d = set(desc_words)
    head = _words(description.split(",")[0])
    score = 0.0
    if q and q <= d:
        score += 3                                   # every query word appears
    score += 2 * len(q & set(head)) / max(len(q), 1)  # query words in the main name
    if head and set(head) <= q:
        score += 2                                   # main name is exactly the query
    score += 0.5 * len((GENERIC & d) - q)
    score -= 1.5 * len((PROCESSED & d) - q)
    score -= 0.4 * len(d - q - GENERIC - PROCESSED)   # other qualifiers the user didn't mention
    if "and" in d and "and" not in q:
        score -= 3                                   # combined dishes ("Beans and white rice", "Rum and diet cola")
    score -= 0.25 * max(description.count(",") - 1, 0)
    if data_type == "Survey (FNDDS)":
        score += 0.75
    elif data_type == "SR Legacy":
        score += 0.25
    return score + min(fdc_score, 2000) / 2000


def rank_hits(query: str, hits: list[SearchHit]) -> list[SearchHit]:
    for h in hits:
        h.rank_score = rank_score(query, h.description, h.data_type, h.fdc_score)
    usable = [h for h in hits if h.calories_per_100g is not None]
    return sorted(usable, key=lambda h: h.rank_score, reverse=True)


def description_confidence(query: str, description: str) -> float:
    """0-1: how well a food description matches what the user typed.

    Missing query words cost the most; extra qualifiers ("Benedict", "fruit") cost a little each.
    """
    q = set(_words(query))
    d = set(_words(description))
    if not q:
        return 0.0
    missing = q - d
    extras = d - q - GENERIC
    conf = 1.0 - 0.6 * len(missing) / len(q) - 0.15 * len(extras) - (0.3 if "and" in extras else 0)
    return round(max(0.05, min(1.0, conf)), 2)


def match_confidence(query: str, ranked: list[SearchHit]) -> float:
    return description_confidence(query, ranked[0].description) if ranked else 0.0


# --- HTTP client ---------------------------------------------------------------------

class FdcClient:
    def __init__(self, api_key: str | None = None, timeout: float = 15.0):
        self.api_key = api_key or os.getenv("FDC_API_KEY")
        if not self.api_key:
            raise FdcError("FDC_API_KEY is not set (see .env.example)")
        self.http = httpx.Client(base_url=BASE_URL, timeout=timeout)

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        for attempt in range(2):                     # FDC has occasional 5xx blips and timeouts; retry once
            try:
                res = self.http.request(method, path, params={"api_key": self.api_key}, **kwargs)
            except httpx.HTTPError as e:
                if attempt:
                    raise FdcError(f"FoodData Central unreachable: {e}") from e
                continue
            if res.status_code < 500 or attempt:
                break
        if res.status_code == 404:
            raise FdcError("Food not found in FoodData Central")
        if res.status_code == 429:
            raise FdcError("FoodData Central rate limit reached; try again later")
        if res.status_code >= 400:
            raise FdcError(f"FoodData Central error {res.status_code}")
        return res.json()

    def search(self, query: str, data_types: list[str] | None = None, page_size: int = 25) -> list[SearchHit]:
        body = {"query": query, "dataType": data_types or PREFERRED_TYPES, "pageSize": page_size}
        data = self._request("POST", "/foods/search", json=body)
        hits = []
        for f in data.get("foods", []):
            kcal = next((_nutrient_value(n) for n in f.get("foodNutrients", []) if _nutrient_number(n) == "208"), None)
            hits.append(SearchHit(f["fdcId"], f["description"], f.get("dataType", ""), kcal, float(f.get("score") or 0)))
        return hits

    def search_ranked(self, query: str) -> list[SearchHit]:
        """FNDDS first; SR Legacy / Foundation only when FNDDS has nothing usable."""
        ranked = rank_hits(query, self.search(query, PREFERRED_TYPES))
        if not ranked or ranked[0].rank_score < 3:
            ranked = sorted(ranked + rank_hits(query, self.search(query, FALLBACK_TYPES)),
                            key=lambda h: h.rank_score, reverse=True)
        return ranked

    def food(self, fdc_id: int) -> Food:
        return parse_food(self._request("GET", f"/food/{fdc_id}"))
