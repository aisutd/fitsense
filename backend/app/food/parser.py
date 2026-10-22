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
from app.food.units import SIZE_UNITS, UNIT_ALIASES, normalize_unit, parse_quantity

MODEL_DIR = Path(__file__).parent / "model"

# Words that can lead a food span but aren't part of the food ("another banana").
LEADING_WORDS = {"another", "my", "the", "more", "extra", "leftover", "leftovers", "homemade", "some", "a", "an", "second", "one"}

# Measures from other logs that the model occasionally tags as FOOD ("slept 8 hours").
NOT_FOOD = {"hour", "hours", "hr", "hrs", "minute", "minutes", "min", "mins", "mile", "miles", "km", "step", "steps",
            "rep", "reps", "set", "sets", "lap", "laps", "day", "days", "week", "weeks"}

# Words the model sometimes pulls into the edge of a FOOD span ("[egg sandwich using]", "[chicken,]").
EDGE_WORDS = {"using", "made", "with", "of", "from", "and", "or", "in", "on", "for", "containing", "contains",
              "consisting", "plus", "which", "that", "had", "was", "&"}

# "egg sandwich using 2 eggs and bread": what follows is what the dish was made of, not more food.
COMPOSITION_WORDS = {"using", "made", "containing", "contains", "consisting"}
CLAUSE_BREAKS = {".", ";", "!", "?", "then", "also", "later", "after", "afterwards", "plus"}

# Food kinds where one replaces another in a recipe ("tofu stir fry" swaps the chicken).
SWAPPABLE = ("protein", "dairy", "grain", "bread")

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
    composed: bool = False          # the player listed this dish's ingredients ("... using 2 eggs and bread")
    part_of: str | None = None      # the dish (as typed) this ingredient was listed under


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


def _clean_ents(doc: Doc) -> list[Span]:
    """Trim punctuation and joining words off FOOD spans and drop non-foods ("slept 8 hours")."""
    out = []
    for e in doc.ents:
        if e.label_ != "FOOD":
            out.append(e)
            continue
        start, end = e.start, e.end
        while start < end and (doc[start].is_punct or doc[start].lower_ in EDGE_WORDS):
            start += 1
        while end > start and (doc[end - 1].is_punct or doc[end - 1].lower_ in EDGE_WORDS):
            end -= 1
        if end > start and doc[start:end].text.lower() not in NOT_FOOD:
            out.extend(_split_list(doc[start:end]))
    return out


def _split_list(span: Span) -> list[Span]:
    """'[chicken and lettuce]' -> chicken, lettuce when both are known foods and the whole isn't
    (so 'mac and cheese' and 'rice and beans' stay one food)."""
    joins = [t.i for t in span if t.lower_ in ("and", "&", ",")]
    if not joins or lexicon.find_food(span.text):
        return [Span(span.doc, span.start, span.end, label="FOOD")]
    parts, start = [], span.start
    for j in joins:
        parts.append((start, j))
        start = j + 1
    parts.append((start, span.end))
    if all(e > s and lexicon.find_food(span.doc[s:e].text) for s, e in parts):
        return [Span(span.doc, s, e, label="FOOD") for s, e in parts]
    return [Span(span.doc, span.start, span.end, label="FOOD")]


def extract_items(doc: Doc) -> list[ParsedItem]:
    ents = _clean_ents(doc)
    items: list[ParsedItem] = []
    pending_qty: float | None = None
    pending_unit: str | None = None
    prev: Span | None = None       # previous entity
    last_food: ParsedItem | None = None
    last_food_span: Span | None = None
    dish: ParsedItem | None = None  # dish whose ingredients are being listed
    skip_until = -1

    for i, ent in enumerate(ents):
        gap = _gap(doc, prev.end, ent.start) if prev is not None else []
        if any(t in CLAUSE_BREAKS for t in gap):
            dish = None
        if i <= skip_until:
            prev = ent
            continue
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
        if dish is not None and dish is not last_food:
            last_food.part_of = dish.text
        elif dish is None:
            following = _gap(doc, ent.end, ents[i + 1].start if i + 1 < len(ents) else len(doc))
            if any(t in COMPOSITION_WORDS for t in following):
                last_food.composed = True
                dish = last_food
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
                           and mod_food.category in SWAPPABLE), None)
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


def _resolve(item: ParsedItem) -> list[ParsedItem]:
    """One extracted item -> recipe ingredients, or itself with its canonical food name."""
    recipes = lexicon.recipes()
    known = lexicon.find_food(item.text)
    if known and known.name in recipes:
        return _expand(known, item, None)
    if known:
        return [replace(item, food_name=known.name)]
    modifier, head = _split_head(item)
    qty = item.quantity if item.quantity is not None else (modifier.quantity if modifier else None)
    unit = item.unit or (modifier.unit if modifier else None)
    if head and head.name in recipes:
        return _expand(head, replace(item, quantity=None if modifier and modifier.quantity is not None and item.quantity is None else item.quantity), modifier)
    if head:
        # "kimchi fried rice": look up as typed, fall back to the known dish
        return [ParsedItem(item.text, qty, unit, fallback_food=head.name)]
    return [ParsedItem(item.text, qty, unit)]


def _swaps_for(ingredient: ParsedItem, default: ParsedItem) -> bool:
    """A listed ingredient replaces a recipe default of the same food or same kind ("rye bread" for "white bread")."""
    if not default.food_name:
        return False
    if not ingredient.food_name:
        # not in foods.json: "rye bread" still replaces the recipe's "whole wheat bread"
        return ingredient.text.lower().split()[-1:] == default.food_name.split()[-1:]
    if ingredient.food_name == default.food_name:
        return True
    foods = lexicon.foods()
    category = foods[ingredient.food_name].category
    return category in SWAPPABLE and category == foods[default.food_name].category


def expand_recipes(items: list[ParsedItem]) -> list[ParsedItem]:
    """Expand dishes that have a recipe and resolve canonical food names."""
    out: list[ParsedItem] = []
    dish_names: dict[str, str] = {}   # dish as typed -> name shown as source_dish
    for item in items:
        resolved = _resolve(item)
        if item.composed:
            recipe_dish = next((r.source_dish for r in resolved if r.source_dish), None)
            dish_names[item.text] = recipe_dish or item.text
            if recipe_dish is None:
                continue    # "egg sandwich using 2 eggs and bread": the listed ingredients *are* the dish
        if item.part_of in dish_names:
            dish = dish_names[item.part_of]
            for r in resolved:
                default = next((o for o in out if o.is_assumed and o.source_dish == dish and _swaps_for(r, o)), None)
                if default is not None:
                    out.remove(default)
                    if r.quantity is None:
                        r.quantity, r.unit = default.quantity, default.unit
                    elif r.unit is None and default.unit in SIZE_UNITS:
                        r.unit = default.unit       # "2 eggs" in a recipe sized in large eggs
                r.source_dish = r.source_dish or dish
        out.extend(resolved)

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
    # dishes first, then foods that aren't part of a dish ("Omelette & Latte")
    names = list(dict.fromkeys([i.source_dish for i in items if i.source_dish] +
                               [i.text for i in items if not i.source_dish and not i.is_assumed]))
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
