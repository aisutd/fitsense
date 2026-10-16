"""Meal text -> ingredients with the trained food model (app/food/model)."""

import pytest

from app.food.parser import parse

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def items(text):
    return [(i.food_name or i.text, i.quantity, i.unit, i.is_assumed) for i in parse(text).items]


def find(meal, name):
    return next(i for i in meal.items if (i.food_name or i.text) == name)


def test_spec_example_omelette_expands_to_adjustable_ingredients():
    meal = parse("I had a 3-egg omelette for breakfast")
    assert meal.meal_type == "breakfast"
    assert meal.display_name == "Omelette"
    egg = find(meal, "egg")
    assert (egg.quantity, egg.unit, egg.is_assumed) == (3, "large", False)     # from the text
    oil = find(meal, "olive oil")
    assert (oil.quantity, oil.unit, oil.is_assumed) == (1, "tsp", True)        # "assumed 1 tsp cooking oil"
    assert find(meal, "cheddar cheese").is_assumed


def test_simple_list_with_units():
    assert items("2 slices of toast with peanut butter and a banana") == [
        ("white bread", 2, "slice", False), ("peanut butter", None, None, False), ("banana", None, None, False),
    ]


def test_grams_and_cups():
    got = items("200g chicken breast, 1 cup rice and broccoli")
    assert got == [("chicken breast", 200, "g", False), ("white rice", 1, "cup", False), ("broccoli", None, None, False)]


def test_half_a_pizza():
    assert items("I ate half a pizza")[0][:2] == ("pizza", 0.5)


def test_size_word_is_a_unit():
    assert items("grabbed a large latte")[0] == ("latte", None, "large", False)


def test_unit_after_the_food():
    got = items("2 eggs, 2 bacon strips, 1 toast")
    assert ("bacon", 2, "piece", False) in got
    assert got[0][:2] == ("egg", 2)


def test_amount_in_brackets_after_the_food():
    assert items("chicken breast (150 g) with rice")[0] == ("chicken breast", 150, "g", False)


def test_mentioned_ingredient_replaces_recipe_default():
    meal = parse("tofu stir fry")
    names = [i.food_name or i.text for i in meal.items]
    assert "tofu" in names and "chicken breast" not in names
    assert find(meal, "tofu").is_assumed is False


def test_recipe_scales_with_count():
    meal = parse("2 omelettes")
    assert find(meal, "egg").quantity == 4


def test_unknown_food_is_kept_as_typed():
    got = parse("pho with beef").items
    assert got[0].text.lower() == "pho" and got[0].food_name is None


def test_unknown_compound_falls_back_to_known_dish():
    item = parse("kimchi fried rice").items[0]
    assert item.fallback_food == "fried rice"


@pytest.mark.parametrize("text, meal_type", [
    ("lunch was a burrito", "lunch"), ("dinner: salmon", "dinner"), ("a snack of almonds", "snack"), ("an apple", None),
])
def test_meal_type(text, meal_type):
    assert parse(text).meal_type == meal_type


@pytest.mark.parametrize("text", ["went for a run today", "skipped breakfast", "slept 8 hours", "walked 3 miles"])
def test_nothing_food_like(text):
    assert parse(text).items == []


@pytest.mark.parametrize("text, want", [
    ("2 tbsp sour cream", ("sour cream", 2, "tbsp")),
    ("peanut butter", ("peanut butter", None, None)),
    ("1 omelette", ("omelette", 1, None)),          # no recipe expansion when adding one ingredient
])
def test_parse_ingredient(text, want):
    from app.food.parser import parse_ingredient
    got = parse_ingredient(text)
    assert (got.text, got.quantity, got.unit) == want
