"""Quantity and unit parsing for meal descriptions."""

import re
from fractions import Fraction

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "half": 0.5, "quarter": 0.25, "dozen": 12, "couple": 2, "few": 3, "several": 3, "single": 1,
    "a": 1, "an": 1,
}
UNICODE_FRACTIONS = {"½": 0.5, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 0.25, "¾": 0.75, "⅛": 0.125}

# alias -> canonical unit
UNIT_ALIASES = {
    "g": "g", "gram": "g", "grams": "g", "gr": "g", "gms": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp", "tsps": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsps": "tbsp", "tbs": "tbsp",
    "cup": "cup", "cups": "cup",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece", "pc": "piece", "pcs": "piece",
    "serving": "serving", "servings": "serving", "portion": "serving", "portions": "serving",
    "bowl": "bowl", "bowls": "bowl",
    "plate": "plate", "plates": "plate", "plateful": "plate",
    "glass": "glass", "glasses": "glass", "mug": "glass", "mugs": "glass",
    "can": "can", "cans": "can",
    "bottle": "bottle", "bottles": "bottle",
    "handful": "handful", "handfuls": "handful",
    "scoop": "scoop", "scoops": "scoop",
    "bag": "bag", "bags": "bag", "bar": "bar", "bars": "bar", "strip": "piece", "strips": "piece",
    "spoonful": "tbsp", "spoonfuls": "tbsp",
    "small": "small", "medium": "medium", "large": "large", "big": "large", "extra large": "extra large",
    "jumbo": "jumbo",
}

# Grams per unit for mass units; millilitres per unit for volume units.
MASS_G = {"g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}
VOLUME_ML = {"ml": 1.0, "l": 1000.0, "tsp": 4.92892, "tbsp": 14.7868, "cup": 236.588, "glass": 240.0,
             "can": 355.0, "bottle": 500.0}
SIZE_UNITS = {"small", "medium", "large", "extra large", "jumbo"}


def parse_quantity(text: str) -> float | None:
    """'3' -> 3, '1/2' -> 0.5, '1 1/2' -> 1.5, '½' -> 0.5, 'two' -> 2, 'a couple of' -> 2,
    'one and a half' -> 1.5, 'two dozen' -> 24. None when there's no number."""
    t = text.lower().strip()
    for ch, value in UNICODE_FRACTIONS.items():
        t = t.replace(ch, f" {value} ")
    # "2-3" / "2 to 3" -> midpoint
    rng = re.fullmatch(r"\D*?(\d+(?:\.\d+)?)\s*(?:-|to|or)\s*(\d+(?:\.\d+)?)\D*", t)
    if rng:
        return (float(rng.group(1)) + float(rng.group(2))) / 2
    total, current, article = 0.0, None, False
    for tok in re.sub(r"[-,]", " ", t).split():
        try:
            current = (current or 0) + float(Fraction(tok))
            article = False
            continue
        except (ValueError, ZeroDivisionError):
            pass
        if tok in ("a", "an"):
            if current is None:
                current, article = 1.0, True
        elif tok in ("half", "quarter"):
            current = NUMBER_WORDS[tok] if (current is None or article) else current * NUMBER_WORDS[tok]
            article = False
        elif tok == "dozen":
            current = (current or 1) * 12
            article = False
        elif tok in ("couple", "few", "several"):
            current, article = float(NUMBER_WORDS[tok]), False
        elif tok in NUMBER_WORDS:
            current = (0 if (current is None or article) else current) + NUMBER_WORDS[tok]
            article = False
        elif tok == "and":
            total += current or 0
            current, article = None, False
    total += current or 0
    return total if total > 0 else None


def normalize_unit(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    t = re.sub(r"\s+", " ", t)
    if t in UNIT_ALIASES:
        return UNIT_ALIASES[t]
    if t.endswith("s") and t[:-1] in UNIT_ALIASES:
        return UNIT_ALIASES[t[:-1]]
    return None


def split_number_unit(text: str) -> tuple[float | None, str | None]:
    """'200g' -> (200, 'g'), '1.5cups' -> (1.5, 'cup')."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*", text)
    if not m:
        return None, None
    return float(m.group(1)), normalize_unit(m.group(2))
