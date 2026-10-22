"""Food logging building blocks that don't need the trained model."""

import json

import pytest

from app.food import lexicon
from app.food.fdc import SearchHit, description_confidence, parse_food, rank_hits, rank_score
from app.food.portions import nutrients, to_grams, unit_options
from app.food.text import prepare_text
from app.food.units import normalize_unit, parse_quantity, split_number_unit

from conftest import FDC_FIXTURES


def food(name: str):
    fid = lexicon.foods()[name].fdc_id
    return parse_food(json.loads((FDC_FIXTURES / f"food_{fid}.json").read_text(encoding="utf-8")))


# --- quantities, units, text ------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("3", 3), ("1.5", 1.5), ("1/2", 0.5), ("1 1/2", 1.5), ("½", 0.5), ("two", 2), ("a couple", 2),
    ("a few", 3), ("half", 0.5), ("a half", 0.5), ("a dozen", 12), ("two dozen", 24), ("one and a half", 1.5),
    ("2-3", 2.5), ("2 or 3", 2.5), ("some", None), ("", None),
])
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Cups", "cup"), ("tbsp.", "tbsp"), ("Tablespoons", "tbsp"), ("grams", "g"), ("big", "large"),
    ("slices", "slice"), ("strips", "piece"), ("handful", "handful"), ("bananas", None), (None, None),
])
def test_normalize_unit(text, expected):
    assert normalize_unit(text) == expected


def test_split_number_unit():
    assert split_number_unit("200g") == (200, "g")
    assert split_number_unit("1.5cups") == (1.5, "cup")
    assert split_number_unit("eggs") == (None, None)


@pytest.mark.parametrize("raw, prepared", [
    ("200g chicken", "200 g chicken"), ("1.5cups rice", "1.5 cups rice"), ("2x eggs", "2 eggs"),
    ("chicken w/ rice", "chicken with rice"), ("a 3-egg omelette", "a 3-egg omelette"), ("  two   eggs ", "two eggs"),
])
def test_prepare_text(raw, prepared):
    assert prepare_text(raw) == prepared


# --- food list & recipes -----------------------------------------------------------------

@pytest.mark.parametrize("text, name", [
    ("Eggs", "egg"), ("coke", "cola"), ("OJ", "orange juice"), ("Strawberry", "strawberries"),
    ("PB&J", "peanut butter sandwich"), ("mac n cheese", "mac and cheese"), ("tomatoes", "tomato"), ("omelet", "omelette"),
])
def test_find_food(text, name):
    assert lexicon.find_food(text).name == name


def test_unknown_food():
    assert lexicon.find_food("kimchi") is None


def test_every_food_is_pinned_and_recipes_are_valid():
    assert all(f.fdc_id for f in lexicon.foods().values())
    for dish, ingredients in lexicon.recipes().items():
        assert dish in lexicon.foods()
        assert all(i.food in lexicon.foods() for i in ingredients)


# --- FoodData Central parsing & ranking --------------------------------------------------------

def test_parse_food_reads_nutrients_and_portions():
    egg = food("egg")
    assert egg.per_100g["calories"] == pytest.approx(143)
    assert egg.per_100g["protein_g"] == pytest.approx(12.56)
    labels = [p.label for p in egg.portions]
    assert "1 large" in labels


def test_ranking_prefers_plain_foods():
    hits = [SearchHit(1, "Bananas, dehydrated, or banana powder", "SR Legacy", 346, 375),
            SearchHit(2, "Banana, raw", "Survey (FNDDS)", 97, 350),
            SearchHit(3, "Banana chips", "Survey (FNDDS)", 519, 340)]
    assert rank_hits("banana", hits)[0].fdc_id == 2


def test_ranking_penalises_combined_dishes():
    assert rank_score("white rice", "Rice, white, cooked", "Survey (FNDDS)") > \
        rank_score("white rice", "Beans and white rice", "Survey (FNDDS)")
    assert rank_score("diet cola", "Soft drink, cola, diet", "Survey (FNDDS)") >         rank_score("diet cola", "Rum and diet cola", "Survey (FNDDS)")


def test_fdc_client_retries_a_server_error_once():
    import httpx
    from app.food.fdc import FdcClient, FdcError
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"foods": []})

    client = FdcClient("test-key")
    client.http = httpx.Client(base_url="https://fdc.test", transport=httpx.MockTransport(handler))
    assert client.search("cola") == [] and len(calls) == 2

    calls.clear()
    client.http = httpx.Client(base_url="https://fdc.test", transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500)))
    with pytest.raises(FdcError):
        client.search("cola")
    assert len(calls) == 2


def test_hits_without_calories_are_dropped():
    assert rank_hits("oil", [SearchHit(1, "Oil, olive", "Foundation", None)]) == []


def test_description_confidence():
    assert description_confidence("banana", "Banana, raw") == 1.0
    assert description_confidence("egg", "Egg, Benedict") < 0.9
    assert description_confidence("pho", "Soup, beef") < 0.6


# --- grams & nutrients ------------------------------------------------------------------

@pytest.mark.parametrize("name, qty, unit, grams", [
    ("egg", 3, "large", 150),               # 3 × 1 large (50 g)
    ("olive oil", 1, "tsp", 4.7),           # FNDDS tablespoon = 14 g -> tsp by volume
    ("cheddar cheese", 20, "g", 20),
    ("banana", 1, None, 126),               # "1 banana"
    ("white bread", 2, "slice", 56),        # "1 medium or regular slice" (28 g), not snack-size
    ("pizza", 2, "slice", 172),             # FDC calls slices "pieces"
    ("bacon", 3, "piece", 24),              # "1 medium slice" (8 g), not "1 cup, pieces"
    ("protein powder", 1, "scoop", 32.3),   # 1/3 cup
    ("peanut butter", 2, "tbsp", 32),
    ("white rice", 1, "cup", 158),
    ("chicken breast", 6, "oz", 170.1),
    ("almonds", 1, "handful", 30),
])
def test_to_grams(name, qty, unit, grams):
    result = to_grams(qty, unit, food(name), name)
    assert result.grams == pytest.approx(grams, abs=0.6)
    assert not result.needs_review


def test_unknown_amount_is_flagged():
    result = to_grams(1, "plate", food("olive oil"), "olive oil")
    assert result.needs_review


def test_drinks_by_volume_are_not_flagged():
    assert not to_grams(1, "can", food("cola"), "cola").needs_review


def test_nutrients_scale_with_grams():
    egg = food("egg")
    n = nutrients(egg, 150)
    assert n["calories"] == pytest.approx(143 * 1.5, abs=0.1)
    assert n["protein_g"] == pytest.approx(12.56 * 1.5, abs=0.1)


def test_mockup_omelette_matches():
    """3 eggs + 1 tsp olive oil + 20 g cheddar ≈ the mockup's 337 kcal / 23.9 g protein."""
    parts = [("egg", 3, "large"), ("olive oil", 1, "tsp"), ("cheddar cheese", 20, "g")]
    total = {"calories": 0.0, "protein_g": 0.0}
    for name, qty, unit in parts:
        f = food(name)
        n = nutrients(f, to_grams(qty, unit, f, name).grams)
        total["calories"] += n["calories"]
        total["protein_g"] += n["protein_g"]
    assert total["calories"] == pytest.approx(337, abs=6)
    assert total["protein_g"] == pytest.approx(23.5, abs=1.5)


def test_unit_options():
    opts = unit_options(food("egg"))
    assert opts[0] == "count" and "g" in opts
