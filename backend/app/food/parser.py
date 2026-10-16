"""Meal text -> ingredients, using the trained spaCy food recogniser (FOOD / QTY / UNIT).

Pipeline: prepare_text -> spaCy NER model -> food-list matcher (adds known foods the model
missed) -> rules that attach quantities and units to foods -> recipe expansion for dishes.
The model is trained by backend/ml/food_ner (see its README). No nutrition happens here.
"""

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span

from app.food import lexicon
from app.food.text import prepare_text
from app.food.units import UNIT_ALIASES, normalize_unit, parse_quantity

MODEL_DIR = Path(__file__).parent / "model"

# Words that can lead a food span but aren't part of the food ("another banana").
LEADING_WORDS = {"another", "my", "the", "more", "extra", "leftover", "leftovers", "homemade", "some", "a", "an", "second", "one"}

# Measures from other logs that the model occasionally tags as FOOD ("slept 8 hours").
NOT_FOOD = {"hour", "hours", "hr", "hrs", "minute", "minutes", "min", "mins", "mile", "miles", "km", "step", "steps",
            "rep", "reps", "set", "sets", "lap", "laps", "day", "days", "week", "weeks"}

SEPARATORS = {",", "and", "with", "&", "+", "plus", ";", "also", "then", "or", "/"}
MEAL_WORDS = {
    "breakfast": "breakfast", "brunch": "breakfast", "lunch": "lunch", "dinner": "dinner", "supper": "dinner",
    "snack": "snack", "dessert": "snack", "pre workout": "snack", "post workout": "snack",
}


@dataclass
class ParsedItem:
    text: str                       # as written, e.g. "eggs"
    quantity: float | None = None   # None = not given (treated as 1 serving)
    unit: str | None = None         # canonical unit, None = count / default portion
    food_name: str | None = None    # canonical name when it's in foods.json
    is_assumed: bool = False        # added by a recipe, not mentioned by the player
    source_dish: str | None = None  # recipe it came from
    fallback_food: str | None = None  # known food to use if "kimchi fried rice" isn't found as typed


@dataclass
class ParsedMeal:
    text: str
    meal_type: str | None
    display_name: str
    items: list[ParsedItem] = field(default_factory=list)


# --- spaCy pipeline -----------------------------------------------------------------

def _plural(word: str) -> str:
    if word.endswith(("s", "sh", "ch")):
        return word
    return word[:-1] + "ies" if re.search(r"[^aeiou]y$", word) else word + "s"


def add_rules(nlp: Language, with_numbers: bool = False) -> Language:
    """Add the food-list matcher. It only fills gaps: spans the model found are never changed.

    with_numbers adds simple QTY/UNIT rules too (used for the no-model baseline in evaluate.py).
    """
    ruler = nlp.add_pipe("entity_ruler", name="food_lexicon", config={"overwrite_ents": False, "phrase_matcher_attr": "LOWER"})
    patterns = []
    for text, _ in lexicon.all_surface_forms():
        for form in {text.lower(), " ".join(text.lower().split()[:-1] + [_plural(text.lower().split()[-1])])}:
            patterns.append({"label": "FOOD", "pattern": form})
    if with_numbers:
        patterns += [
            {"label": "QTY", "pattern": [{"LIKE_NUM": True}, {"ORTH": "-"}, {"LIKE_NUM": True}]},
            {"label": "QTY", "pattern": [{"LIKE_NUM": True}]},
            {"label": "QTY", "pattern": [{"LOWER": {"IN": ["½", "¼", "¾", "half"]}}]},
            {"label": "QTY", "pattern": [{"LOWER": "a"}, {"LOWER": {"IN": ["couple", "few", "dozen", "half"]}}]},
            {"label": "UNIT", "pattern": [{"LOWER": {"IN": sorted(k for k in UNIT_ALIASES if " " not in k)}}]},
        ]
    ruler.add_patterns(patterns)
    return nlp


@lru_cache
def get_nlp() -> Language:
    if not MODEL_DIR.exists():
        raise RuntimeError(f"Food model not found at {MODEL_DIR}. Train it: see backend/ml/food_ner/README.md")
    return add_rules(spacy.load(MODEL_DIR))


# --- attaching quantities and units ----------------------------------------------------

def _gap(doc: Doc, start: int, end: int) -> list[str]:
    return [t.lower_ for t in doc[start:end]]


def _has_separator(tokens: list[str]) -> bool:
    return any(t in SEPARATORS for t in tokens)


def _is_trailing(doc: Doc, ents: list[Span], idx: int) -> bool:
    """True when the QTY/UNIT run starting at ents[idx] describes the food *before* it
    ("chicken (150 g)"), i.e. no food follows it before a separator or the end."""
    k = idx
    while k + 1 < len(ents) and ents[k + 1].label_ in ("QTY", "UNIT") and not _has_separator(_gap(doc, ents[k].end, ents[k + 1].start)):
        k += 1
    if k + 1 >= len(ents):
        return True
    nxt = ents[k + 1]
    gap = _gap(doc, ents[k].end, nxt.start)
    return nxt.label_ != "FOOD" or _has_separator(gap)


def _food_text(span: Span) -> str:
    words = span.text.split()
    while len(words) > 1 and words[0].lower() in LEADING_WORDS:
        words = words[1:]
    return " ".join(words)


# Piece words that sometimes end up inside the FOOD span ("2 [bacon strips]") instead of UNIT.
TRAILING_PIECES = {"strip", "strips", "slice", "slices", "piece", "pieces"}


def _new_item(span: Span, qty: float | None, unit: str | None) -> ParsedItem:
    text = _food_text(span)
    words = text.split()
    if unit is None and len(words) > 1 and words[-1].lower() in TRAILING_PIECES:
        text, unit = " ".join(words[:-1]), normalize_unit(words[-1])
    return ParsedItem(text, qty, unit)


def extract_items(doc: Doc) -> list[ParsedItem]:
    ents = [e for e in doc.ents if not (e.label_ == "FOOD" and e.text.lower() in NOT_FOOD)]
    items: list[ParsedItem] = []
    pending_qty: float | None = None
    pending_unit: str | None = None
    prev: Span | None = None       # previous entity
    last_food: ParsedItem | None = None
    last_food_span: Span | None = None
    skip_until = -1

    for i, ent in enumerate(ents):
        if i <= skip_until:
            prev = ent
            continue
        gap = _gap(doc, prev.end, ent.start) if prev is not None else []
        if prev is not None and _has_separator(gap):
            pending_qty, pending_unit = None, None

        if ent.label_ in ("QTY", "UNIT"):
            after_food = last_food is not None and prev is not None and prev.label_ == "FOOD"
            if after_food and last_food.unit is None and _is_trailing(doc, ents, i) and not _has_separator(gap):
                # "chicken (150 g)", "2 bacon strips", "rice 1 cup"
                k = i
                while True:
                    e = ents[k]
                    if e.label_ == "QTY" and (last_food.quantity is None or k > i):
                        last_food.quantity = parse_quantity(e.text)
                    elif e.label_ == "UNIT":
                        last_food.unit = normalize_unit(e.text)
                    if k + 1 < len(ents) and ents[k + 1].label_ in ("QTY", "UNIT") and not _has_separator(_gap(doc, e.end, ents[k + 1].start)):
                        k += 1
                    else:
                        break
                skip_until = k
            elif ent.label_ == "QTY":
                pending_qty = parse_quantity(ent.text)
            else:
                pending_unit = normalize_unit(ent.text)
            prev = ent
            continue

        # FOOD
        adjacent_food = (prev is not None and prev.label_ == "FOOD" and last_food_span is prev
                         and all(t in ("-",) for t in gap))
        if adjacent_food:
            # "3-egg omelette", "spinach omelet", "kimchi fried rice": modifier + head
            modifier = items.pop()
            head = _new_item(ent, pending_qty, pending_unit)
            items.append(_compound(modifier, head))
            last_food = items[-1]
        else:
            last_food = _new_item(ent, pending_qty, pending_unit)
            items.append(last_food)
        last_food_span = ent
        pending_qty, pending_unit = None, None
        prev = ent
    return items


def _compound(modifier: ParsedItem, head: ParsedItem) -> ParsedItem:
    """Keep the pair together; recipe expansion decides how to use the modifier."""
    head = replace(head, text=f"{modifier.text} {head.text}")
    head._modifier = modifier  # type: ignore[attr-defined]
    return head


# --- recipes ----------------------------------------------------------------------

def _split_head(item: ParsedItem) -> tuple[ParsedItem | None, lexicon.KnownFood | None]:
    """'3-egg omelette' / 'spinach omelet' / 'kimchi fried rice' -> (modifier, known head food)."""
    modifier: ParsedItem | None = getattr(item, "_modifier", None)
    if modifier is not None:
        return modifier, lexicon.find_food(item.text[len(modifier.text) + 1:])
    words = item.text.split()
    for k in range(1, len(words)):
        head = lexicon.find_food(" ".join(words[k:]))
        if head:
            return ParsedItem(" ".join(words[:k])), head
    return None, None


def _expand(dish: lexicon.KnownFood, item: ParsedItem, modifier: ParsedItem | None) -> list[ParsedItem]:
    recipe = lexicon.recipes()[dish.name]
    foods = lexicon.foods()
    scale = item.quantity if (item.quantity and item.unit is None) else 1.0
    replaces: dict[str, ParsedItem] = {}
    extras: list[ParsedItem] = []
    if modifier is not None:
        mod_food = lexicon.find_food(modifier.text)
        mod_item = ParsedItem(modifier.text, modifier.quantity, modifier.unit,
                              mod_food.name if mod_food else None, source_dish=dish.name)
        # Same food ("3-egg omelette") or same kind of food ("tofu stir fry" swaps the chicken)
        target = next((ing.food for ing in recipe if mod_food and ing.food == mod_food.name), None)
        if target is None and mod_food:
            target = next((ing.food for ing in recipe if foods[ing.food].category == mod_food.category
                           and mod_food.category in ("protein", "dairy", "grain", "bread")), None)
        if target:
            replaces[target] = mod_item
        else:
            extras.append(mod_item)

    out = []
    for ing in recipe:
        if ing.food in replaces:
            r = replaces[ing.food]
            if r.quantity is not None:
                qty, unit = r.quantity, r.unit if r.unit is not None else (ing.unit if ing.unit in ("large", "medium", "small") else None)
            else:
                qty, unit = ing.quantity * scale, ing.unit
            out.append(ParsedItem(r.text, qty, unit, r.food_name, is_assumed=False, source_dish=dish.name))
        else:
            out.append(ParsedItem(ing.food, ing.quantity * scale, ing.unit, ing.food, is_assumed=True, source_dish=dish.name))
    return out + extras


def expand_recipes(items: list[ParsedItem]) -> list[ParsedItem]:
    """Expand dishes that have a recipe and resolve canonical food names."""
    out: list[ParsedItem] = []
    recipes = lexicon.recipes()
    for item in items:
        known = lexicon.find_food(item.text)
        if known and known.name in recipes:
            out.extend(_expand(known, item, None))
            continue
        if known:
            out.append(replace(item, food_name=known.name))
            continue
        modifier, head = _split_head(item)
        qty = item.quantity if item.quantity is not None else (modifier.quantity if modifier else None)
        unit = item.unit or (modifier.unit if modifier else None)
        if head and head.name in recipes:
            out.extend(_expand(head, replace(item, quantity=None if modifier and modifier.quantity is not None and item.quantity is None else item.quantity), modifier))
        elif head:
            # "kimchi fried rice": look up as typed, fall back to the known dish
            out.append(ParsedItem(item.text, qty, unit, fallback_food=head.name))
        else:
            out.append(ParsedItem(item.text, qty, unit))

    # An ingredient the player mentioned separately replaces the recipe's assumed default.
    explicit = {i.food_name for i in out if not i.is_assumed and i.food_name}
    return [i for i in out if not (i.is_assumed and i.food_name in explicit)]


def detect_meal_type(text: str) -> str | None:
    t = text.lower()
    for word, meal in MEAL_WORDS.items():
        if re.search(rf"\b{word}\b", t):
            return meal
    return None


def display_name(items: list[ParsedItem]) -> str:
    dishes = list(dict.fromkeys(i.source_dish for i in items if i.source_dish))
    names = dishes or list(dict.fromkeys(i.text for i in items if not i.is_assumed))
    if not names:
        return "Meal"
    title = " & ".join(n.title() for n in names[:2])
    return title + (" + more" if len(names) > 2 else "")


def parse_ingredient(text: str) -> ParsedItem:
    """One ingredient typed on the review card ("2 tbsp sour cream"). No recipe expansion: the player is
    adding exactly this. Falls back to the whole text as the food when the model finds nothing."""
    items = extract_items(get_nlp()(prepare_text(text)))
    item = items[0] if items else ParsedItem(text.strip())
    known = lexicon.find_food(item.text)
    return replace(item, food_name=known.name) if known else item


def parse(text: str) -> ParsedMeal:
    prepared = prepare_text(text)
    doc = get_nlp()(prepared)
    items = expand_recipes(extract_items(doc))
    return ParsedMeal(text=text, meal_type=detect_meal_type(prepared), display_name=display_name(items), items=items)
