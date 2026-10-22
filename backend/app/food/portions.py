"""Quantity + unit -> grams, using a food's FoodData Central portions, and nutrients for those grams."""

import re
from dataclasses import dataclass

from app.food.fdc import Food, Portion
from app.food.units import MASS_G, SIZE_UNITS, VOLUME_ML

CUP_ML = VOLUME_ML["cup"]
SIZE_FACTOR = {"small": 0.8, "medium": 1.0, "large": 1.2, "extra large": 1.35, "jumbo": 1.5}
UNIT_WORDS = {
    "tsp": ("teaspoon", "tsp"), "tbsp": ("tablespoon", "tbsp"), "cup": ("cup",),
    "slice": ("slice", "piece"), "piece": ("piece", "strip", "nugget", "wing", "slice"), "scoop": ("scoop",), "bowl": ("bowl",),
    "bar": ("bar",), "bag": ("bag", "package", "packet"), "can": ("can",), "bottle": ("bottle",),
    "glass": ("glass",), "serving": ("serving",), "plate": ("plate",),
}
DEFAULT_SERVING = "quantity not specified"


@dataclass
class Grams:
    grams: float
    label: str            # what was used, e.g. "1 large (50 g)"
    needs_review: bool    # True when we had to guess


GOOD = {"medium": 2.0, "regular": 2.0, "nfs": 1.5, "fruit": 1.5, "whole": 1.0, "each": 1.0, "piece": 0.5}
BAD = {"small": -1.5, "thin": -1.5, "snack": -3.0, "mini": -3.0, "miniature": -3.0, "bite": -3.0, "silver": -3.0,
       "crust": -2.0, "personal": -1.0, "large": -0.5, "extra": -1.5, "thick": -1.0, "guideline": -3.0,
       "surface": -5.0, "cubic": -5.0, "inch": -5.0, "package": -1.0, "raw": -0.5}
VOLUME_WORDS = ("cup", "tablespoon", "teaspoon", "tbsp", "tsp", "fl oz", "oz")


def _label_score(label: str, food_words: tuple[str, ...] = ()) -> float:
    words = re.findall(r"[a-z]+", label.lower())
    score = sum(GOOD.get(w, 0) + BAD.get(w, 0) for w in words)
    if any(w.rstrip("s") in food_words for w in words):
        score += 2.5
    return score - 0.01 * len(label)


def _portions_with(food: Food, words: tuple[str, ...], exclude_volume: bool = False) -> list[Portion]:
    found = [p for p in food.portions if any(re.search(rf"\b{w}s?\b", p.label.lower()) for w in words)]
    if exclude_volume:
        found = [p for p in found if not any(v in p.label.lower() for v in VOLUME_WORDS)]
    return sorted(found, key=lambda p: _label_score(p.label), reverse=True)


def _per_one(p: Portion) -> float:
    return p.gram_weight / (p.amount or 1)


def _grams_per_ml(food: Food) -> float | None:
    for unit in ("cup", "tbsp", "tsp"):
        ps = [p for p in _portions_with(food, UNIT_WORDS[unit]) if not re.search(r"\b(chopped|sliced|diced|mashed|cubed|shredded|crumbled|pieces)\b", p.label.lower())]
        ps = ps or _portions_with(food, UNIT_WORDS[unit])
        if ps:
            return _per_one(ps[0]) / VOLUME_ML[unit]
    return None


def _count_portion(food: Food, item_text: str) -> Portion | None:
    """The portion for 'one of these': '1 banana', '1 fruit', '1 medium', '1 hamburger', '1 nugget'."""
    food_words = tuple(w.rstrip("s") for w in re.findall(r"[a-z]+", (item_text + " " + food.description).lower()) if len(w) > 2)
    candidates = [
        p for p in food.portions
        if p.label.lower().startswith("1 ") and not any(v in p.label.lower() for v in VOLUME_WORDS)
        and _label_score(p.label, food_words) > -2
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: _label_score(p.label, food_words))


def _default_serving(food: Food) -> Portion | None:
    ps = [p for p in food.portions if DEFAULT_SERVING in p.label.lower()]
    return ps[0] if ps else (_portions_with(food, ("serving",)) or [None])[0]


def to_grams(quantity: float | None, unit: str | None, food: Food, item_text: str = "") -> Grams:
    qty = quantity if quantity and quantity > 0 else 1.0
    fmt = lambda g: f"{g:.0f} g" if g >= 10 else f"{g:.1f} g"  # noqa: E731

    if unit in MASS_G:
        g = qty * MASS_G[unit]
        return Grams(g, f"{qty:g} {unit}", False)

    if unit in ("tsp", "tbsp", "cup"):
        ps = _portions_with(food, UNIT_WORDS[unit])
        if ps:
            g = qty * _per_one(ps[0])
            return Grams(g, f"{qty:g} × {ps[0].label} ({fmt(_per_one(ps[0]))})", False)
    if unit in VOLUME_ML:
        per_ml = _grams_per_ml(food)
        ml = qty * VOLUME_ML[unit]
        if per_ml:
            return Grams(ml * per_ml, f"{qty:g} {unit} ≈ {ml:.0f} ml", False)
        return Grams(ml, f"{qty:g} {unit} ≈ {ml:.0f} ml", unit not in ("glass", "can", "bottle", "ml", "l"))

    if unit in SIZE_UNITS:
        ps = [p for p in food.portions if re.search(rf"\b{unit}\b", p.label.lower()) and "cup" not in p.label.lower()]
        if ps:
            p = sorted(ps, key=lambda p: len(p.label))[0]
            return Grams(qty * _per_one(p), f"{qty:g} × {p.label} ({fmt(_per_one(p))})", False)
        p = _count_portion(food, item_text)
        if p:
            g = qty * _per_one(p) * SIZE_FACTOR[unit]
            return Grams(g, f"{qty:g} {unit} ≈ {fmt(g / qty)} each", False)

    if unit == "scoop" and not _portions_with(food, ("scoop",)):
        cup = _portions_with(food, ("cup",))
        if cup:
            g = qty * _per_one(cup[0]) / 3
            return Grams(g, f"{qty:g} scoop ≈ 1/3 cup ({fmt(g / qty)})", False)
    if unit in UNIT_WORDS:
        words = UNIT_WORDS[unit] + (("slice", "strip", "nugget") if unit == "piece" else ())
        ps = _portions_with(food, words, exclude_volume=unit in ("slice", "piece", "bar", "scoop"))
        if ps:
            return Grams(qty * _per_one(ps[0]), f"{qty:g} × {ps[0].label} ({fmt(_per_one(ps[0]))})", False)
        if unit == "bowl":
            cup = _portions_with(food, ("cup",))
            if cup:
                g = qty * 1.5 * _per_one(cup[0])
                return Grams(g, f"{qty:g} bowl ≈ 1.5 cups", False)
        if unit in ("serving", "plate", "bag", "bar"):
            p = _default_serving(food)
            if p:
                factor = 1.5 if unit == "plate" else 1.0
                return Grams(qty * factor * _per_one(p), f"{qty:g} {unit} ≈ typical serving ({fmt(_per_one(p) * factor)})", unit == "plate")
    if unit == "handful":
        return Grams(qty * 30, f"{qty:g} handful ≈ 30 g", False)

    if unit is None:
        p = _count_portion(food, item_text)
        if p:
            return Grams(qty * _per_one(p), f"{qty:g} × {p.label} ({fmt(_per_one(p))})", False)
        p = _default_serving(food)
        if p:
            return Grams(qty * _per_one(p), f"{qty:g} × typical serving ({fmt(_per_one(p))})", False)

    # Nothing to go on: one 100 g serving, flagged for the player to adjust.
    return Grams(qty * 100.0, f"{qty:g} {unit or 'serving'} ≈ 100 g (estimate - please adjust)", True)


def nutrients(food: Food, grams: float) -> dict:
    """Nutrients for `grams` of the food, from FDC's per-100 g values."""
    f = grams / 100.0
    return {k: round((food.per_100g.get(k) or 0.0) * f, 1) for k in ("calories", "protein_g", "carbs_g", "fat_g")}


def unit_options(food: Food) -> list[str]:
    """Units the player can switch between for this food."""
    options = ["g", "oz"]
    labels = " ".join(p.label.lower() for p in food.portions)
    if _count_portion(food, food.description) or _default_serving(food):
        options.insert(0, "count")
    for unit in ("cup", "tbsp", "tsp", "slice", "piece", "scoop"):
        if any(re.search(rf"\b{w}s?\b", labels) for w in UNIT_WORDS[unit]):
            options.append(unit)
    if _grams_per_ml(food) is not None:
        options.append("ml")
    return list(dict.fromkeys(options))
