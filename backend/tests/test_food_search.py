"""The local USDA copy (importer + search) and search-as-you-type / picking foods."""

import io
import json
import zipfile
from uuid import uuid4

import pytest

from app.food import lexicon
from app.food.fdc import parse_food, rank_score
from app.food.fdc_import import _stream_array, import_foods, read_foods

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

DAY = "2026-10-22"
PROFILE = {
    "age": 21, "height_cm": 175.0, "weight_kg": 70.0, "fitness_goal": "build_muscle",
    "fitness_level": "beginner", "workout_frequency": 4, "workout_location": "gym",
}


def pinned(name):
    return lexicon.foods()[name].fdc_id


def raw_food(fdc_id, description, kcal_number="208", kcal=100.0, portions=()):
    return {"fdcId": fdc_id, "description": description, "dataType": "Foundation",
            "foodNutrients": [{"nutrient": {"number": kcal_number}, "amount": kcal},
                              {"nutrient": {"number": "203"}, "amount": 5.0}],
            "foodPortions": [{"portionDescription": label, "gramWeight": g, "id": k} for k, (label, g) in enumerate(portions)]}


@pytest.fixture
def no_api():
    """No FDC_API_KEY: everything must come from the local copy."""
    from app.main import app
    from app.routers.meals import get_fdc
    app.dependency_overrides[get_fdc] = lambda: None
    yield


@pytest.fixture
def user(client):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


# --- importer ----------------------------------------------------------------------------

def test_stream_reads_a_large_array_in_small_chunks():
    foods = [raw_food(i, f"Food {i}, with a long enough description to span chunks") for i in range(50)]
    text = json.dumps({"SurveyFoods": foods[:25] + [None] + foods[25:]})
    got = [f for f in _stream_array(io.StringIO(text), chunk_size=64)]
    assert [f["fdcId"] for f in got if f] == list(range(50))


def test_read_foods_from_a_dataset_zip(tmp_path):
    path = tmp_path / "foundation.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("foundation.json", json.dumps({"FoundationFoods": [raw_food(1, "Hummus"), None]}))
    assert [f["description"] for f in read_foods(path)] == ["Hummus"]


def test_foundation_energy_falls_back_to_atwater():
    food = parse_food(raw_food(1, "Hummus, commercial", kcal_number="958", kcal=229.0))
    assert food.per_100g["calories"] == 229.0


def test_import_writes_foods_and_replaces_portions(fake_db):
    import_foods(fake_db, [raw_food(1, "Oats", portions=[("1 cup", 81.0)]), raw_food(2, "No energy", kcal_number="999")],
                 log=lambda *_: None)
    import_foods(fake_db, [raw_food(1, "Oats", portions=[("1 cup", 81.0), ("1 tbsp", 5.0)])], log=lambda *_: None)
    foods = fake_db.tables["fdc_foods"]
    assert set(foods) == {1} and foods[1]["source"] == "import"            # foods without kcal are skipped
    portions = [p["label"] for p in fake_db.tables["fdc_food_portions"].values()]
    assert sorted(portions) == ["1 cup", "1 tbsp"]                          # re-import didn't duplicate


# --- local search ------------------------------------------------------------------------

def test_ranking_completes_a_half_typed_word():
    assert rank_score("chicken bre", "Chicken breast, baked", "Survey (FNDDS)", partial=True) > \
        rank_score("chicken bre", "Chicken thigh, baked", "Survey (FNDDS)", partial=True)


def test_lexicon_suggest():
    assert lexicon.suggest("bana")[0] == (lexicon.foods()["banana"], "banana")
    assert lexicon.suggest("oj")[0][0].name == "orange juice"        # aliases count
    assert "peanut butter" in [f.name for f, _ in lexicon.suggest("pean but")]
    # shown under the alias that matched, not a name that doesn't contain what was typed
    assert all(label.startswith("gre") or " gre" in label for _, label in lexicon.suggest("gre"))


def test_analyze_uses_the_local_copy_without_the_api(client, user, usda_copy, no_api):
    res = client.post(f"/meals/{user}/analyze", json={"text": "I had a 3-egg omelette", "log_date": DAY})
    assert res.status_code == 200, res.text
    assert res.json()["totals"]["calories"] == pytest.approx(337, abs=6)


def test_unknown_food_is_found_in_the_local_copy(client, user, usda_copy, no_api):
    meal = client.post(f"/meals/{user}/analyze", json={"text": "a bowl of pho", "log_date": DAY}).json()
    assert "pho" in meal["items"][0]["food"]["description"].lower()


def test_food_missing_locally_without_api_is_a_clear_error(client, user, fake_db, no_api):
    res = client.post(f"/meals/{user}/analyze", json={"text": "a banana", "log_date": DAY})
    assert res.status_code == 503 and "fdc_import" in res.json()["detail"]


# --- search as you type ------------------------------------------------------------------

def test_suggest_lists_known_foods_first(client, usda_copy, no_api):
    got = client.get("/foods/suggest", params={"q": "bana"}).json()
    assert got[0]["name"] == "Banana" and got[0]["source"] == "list" and got[0]["calories_per_100g"]
    assert len({g["fdc_id"] for g in got}) == len(got)                      # no duplicates


def test_suggest_includes_usda_foods(client, usda_copy, no_api):
    got = client.get("/foods/suggest", params={"q": "ph"}).json()
    assert any(g["source"] == "usda" and "pho" in g["description"].lower() for g in got)


def test_suggest_hides_duplicate_descriptions(client, usda_copy, no_api):
    usda_copy.tables["fdc_foods"][1] = {"fdc_id": 1, "description": "Banana, raw", "data_type": "SR Legacy",
                                        "calories_per_100g": 89.0, "source": "import"}
    got = client.get("/foods/suggest", params={"q": "banana r"}).json()
    assert [g["description"] for g in got].count("Banana, raw") == 1


def test_suggest_needs_two_characters(client, usda_copy, no_api):
    assert client.get("/foods/suggest", params={"q": "a"}).json() == []


def test_start_a_meal_from_picked_foods(client, user, usda_copy, no_api):
    res = client.post(f"/meals/{user}/start", json={"log_date": DAY, "meal_type": "snack", "items": [
        {"fdc_id": pinned("banana")}, {"fdc_id": pinned("peanut butter"), "quantity": 2, "unit": "tbsp"}]})
    assert res.status_code == 200, res.text
    meal = res.json()
    assert meal["status"] == "estimated" and meal["display_name"] == "Banana & Peanut butter"
    banana, pb = meal["items"]
    assert banana["ingredient_text"] == "banana" and banana["match_confidence"] == 1.0 and not banana["needs_review"]
    assert pb["grams"] == 32 and meal["totals"]["calories"] > 250


def test_add_a_picked_food(client, user, usda_copy, no_api):
    meal = client.post(f"/meals/{user}/start", json={"log_date": DAY, "items": [{"fdc_id": pinned("banana")}]}).json()
    added = client.post(f"/meals/{meal['meal_id']}/items", json={"fdc_id": pinned("almonds"), "quantity": 30, "unit": "g"}).json()
    assert [i["ingredient_text"] for i in added["items"]] == ["banana", "almonds"]
    assert added["items"][1]["grams"] == 30


@pytest.mark.parametrize("body", [
    {"log_date": DAY, "items": []},
    {"log_date": DAY, "items": [{"quantity": 2}]},                          # neither text nor food
    {"log_date": DAY, "items": [{"fdc_id": -5}]},
])
def test_start_meal_validation(client, user, usda_copy, no_api, body):
    assert client.post(f"/meals/{user}/start", json=body).status_code == 422


def test_start_meal_with_a_food_we_dont_have(client, user, usda_copy, no_api):
    res = client.post(f"/meals/{user}/start", json={"log_date": DAY, "items": [{"fdc_id": 99999999}]})
    assert res.status_code == 503
    assert client.get("/meals", params={"user_id": user, "log_date": DAY}).json() == []   # no empty meal left behind


def test_start_meal_unknown_user(client, usda_copy, no_api):
    res = client.post(f"/meals/{uuid4()}/start", json={"log_date": DAY, "items": [{"fdc_id": pinned("banana")}]})
    assert res.status_code == 404


def test_swapping_a_picked_food_renames_it(client, user, usda_copy, no_api):
    meal = client.post(f"/meals/{user}/start", json={"log_date": DAY, "items": [{"fdc_id": pinned("banana")}]}).json()
    item = meal["items"][0]
    swapped = client.patch(f"/meals/{meal['meal_id']}/items/{item['meal_item_id']}", json={"fdc_id": pinned("apple")}).json()
    assert swapped["items"][0]["ingredient_text"] == "apple" and swapped["display_name"] == "Apple"


def test_typed_names_survive_a_swap(client, user, usda_copy, no_api):
    meal = client.post(f"/meals/{user}/analyze", json={"text": "2 eggs", "log_date": DAY}).json()
    item = meal["items"][0]
    swapped = client.patch(f"/meals/{meal['meal_id']}/items/{item['meal_item_id']}", json={"fdc_id": pinned("cheddar cheese")}).json()
    assert swapped["items"][0]["ingredient_text"] == "eggs" and swapped["display_name"] == meal["display_name"]


def test_picked_meal_name_follows_its_items(client, user, usda_copy, no_api):
    meal = client.post(f"/meals/{user}/start", json={"log_date": DAY, "items": [{"fdc_id": pinned("banana")}]}).json()
    added = client.post(f"/meals/{meal['meal_id']}/items", json={"fdc_id": pinned("almonds")}).json()
    assert added["display_name"] == "Banana & Almonds"
    first = added["items"][0]["meal_item_id"]
    assert client.delete(f"/meals/{meal['meal_id']}/items/{first}").json()["display_name"] == "Almonds"
