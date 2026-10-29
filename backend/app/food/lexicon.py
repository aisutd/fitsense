"""Known foods (pinned to FoodData Central ids) and dish recipes, loaded from app/food/data."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class KnownFood:
    name: str
    aliases: tuple[str, ...]
    query: str
    category: str
    fdc_id: int | None = None
    fdc_description: str | None = None


@dataclass(frozen=True)
class RecipeIngredient:
    food: str
    quantity: float
    unit: str | None


def normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("oes", "ches", "shes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _variants(text: str) -> list[str]:
    norm = normalize(text)
    words = norm.split()
    if not words:
        return []
    singular_last = " ".join(words[:-1] + [_singular(words[-1])])
    return list(dict.fromkeys([norm, singular_last, " ".join(_singular(w) for w in words)]))


@lru_cache
def foods() -> dict[str, KnownFood]:
    raw = json.loads((DATA_DIR / "foods.json").read_text(encoding="utf-8"))["foods"]
    return {
        f["name"]: KnownFood(f["name"], tuple(f.get("aliases", [])), f["query"], f["category"],
                             f.get("fdc_id"), f.get("fdc_description"))
        for f in raw
    }


@lru_cache
def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for food in foods().values():
        for alias in (food.name, *food.aliases):
            for v in _variants(alias):
                index.setdefault(v, food.name)
    return index


def find_food(text: str) -> KnownFood | None:
    """'Eggs' -> egg, 'coke' -> cola, 'OJ' -> orange juice."""
    index = _alias_index()
    for v in _variants(text):
        if v in index:
            return foods()[index[v]]
    return None


@lru_cache
def recipes() -> dict[str, tuple[RecipeIngredient, ...]]:
    raw = json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))["recipes"]
    known = foods()
    out = {}
    for dish, ingredients in raw.items():
        assert dish in known, f"recipe '{dish}' isn't in foods.json"
        for ing in ingredients:
            assert ing["food"] in known, f"recipe '{dish}' uses unknown food '{ing['food']}'"
        out[dish] = tuple(RecipeIngredient(i["food"], float(i["quantity"]), i["unit"]) for i in ingredients)
    return out


def all_surface_forms() -> list[tuple[str, str]]:
    """(text, canonical name) for every name and alias - used for training data and the backup matcher."""
    return [(alias, f.name) for f in foods().values() for alias in (f.name, *f.aliases)]
