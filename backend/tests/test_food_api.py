"""Food logging endpoints, with a fake Supabase and recorded FoodData Central responses."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

DAY = "2026-10-15"
PROFILE = {
    "age": 21, "height_cm": 175.0, "weight_kg": 70.0, "fitness_goal": "build_muscle",
    "fitness_level": "beginner", "workout_frequency": 4, "workout_location": "gym",
}


@pytest.fixture
def user(client, fake_fdc):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


def analyze(client, uid, text, **extra):
    return client.post(f"/meals/{uid}/analyze", json={"text": text, "log_date": DAY, **extra})


def item(meal, name):
    return next(i for i in meal["items"] if i["ingredient_text"] == name)


def test_analyze_mockup_omelette(client, user, fake_db):
    res = analyze(client, user, "I had a 3-egg omelette for breakfast")
    assert res.status_code == 200, res.text
    meal = res.json()
    assert meal["status"] == "estimated" and meal["meal_type"] == "breakfast" and meal["display_name"] == "Omelette"
    egg = item(meal, "egg")
    assert egg["grams"] == 150 and egg["food"]["description"] == "Egg, whole, raw, fresh"
    assert egg["is_assumed"] is False and egg["needs_review"] is False
    assert item(meal, "olive oil")["is_assumed"] is True
    # ≈ the mockup's 337 kcal / 23.9 g protein, all from FoodData Central values
    assert meal["totals"]["calories"] == pytest.approx(337, abs=6)
    assert meal["totals"]["protein_g"] == pytest.approx(23.5, abs=1.5)
    # stored as an estimate, cached FDC foods
    stored = fake_db.tables["meal_entries"][meal["meal_id"]]
    assert stored["status"] == "estimated" and stored["raw_text"].startswith("I had")
    assert 171287 in fake_db.tables["fdc_foods"]


def test_dish_with_listed_ingredients_is_not_double_counted(client, user):
    meal = analyze(client, user, "I had an egg sandwich using 2 eggs and 2 slices of white bread.").json()
    assert meal["display_name"] == "Egg Sandwich" and len(meal["items"]) == 3
    assert item(meal, "eggs")["grams"] == 100 and item(meal, "white bread")["grams"] == 56
    assert item(meal, "butter")["is_assumed"] is True
    assert meal["totals"]["calories"] == pytest.approx(327, abs=15)   # eggs 143 + bread 150 + butter ~34


def test_fdc_foods_are_cached(client, user, fake_fdc):
    analyze(client, user, "a banana")
    calls = len(fake_fdc.calls)
    analyze(client, user, "another banana")
    assert len(fake_fdc.calls) == calls          # second lookup served from Supabase


def test_adjust_quantity_updates_totals(client, user):
    meal = analyze(client, user, "I had a 3-egg omelette").json()
    egg = item(meal, "egg")
    res = client.patch(f"/meals/{meal['meal_id']}/items/{egg['meal_item_id']}", json={"quantity": 2})
    assert res.status_code == 200
    updated = res.json()
    assert item(updated, "egg")["grams"] == 100
    assert updated["totals"]["calories"] == pytest.approx(meal["totals"]["calories"] - 71.5, abs=1)


def test_change_unit(client, user):
    meal = analyze(client, user, "1 cup rice").json()
    rice = meal["items"][0]
    updated = client.patch(f"/meals/{meal['meal_id']}/items/{rice['meal_item_id']}", json={"quantity": 100, "unit": "g"}).json()
    assert updated["items"][0]["grams"] == 100


def test_unknown_food_uses_search_and_can_be_swapped(client, user):
    meal = analyze(client, user, "pho").json()
    pho = meal["items"][0]
    assert pho["food"] is not None and pho["alternatives"]
    choice = pho["alternatives"][-1]["fdc_id"]
    updated = client.patch(f"/meals/{meal['meal_id']}/items/{pho['meal_item_id']}", json={"fdc_id": choice}).json()
    assert updated["items"][0]["food"]["fdc_id"] == choice
    assert updated["items"][0]["needs_review"] is False


def test_add_and_remove_ingredients(client, user):
    meal = analyze(client, user, "a banana").json()
    added = client.post(f"/meals/{meal['meal_id']}/items", json={"text": "peanut butter", "quantity": 2, "unit": "tbsp"}).json()
    assert len(added["items"]) == 2 and added["totals"]["calories"] > meal["totals"]["calories"]
    pb = item(added, "peanut butter")
    removed = client.delete(f"/meals/{meal['meal_id']}/items/{pb['meal_item_id']}").json()
    assert len(removed["items"]) == 1 and removed["totals"] == meal["totals"]


def test_add_ingredient_typed_in_one_box(client, user):
    meal = analyze(client, user, "a banana").json()
    added = client.post(f"/meals/{meal['meal_id']}/items", json={"text": "2 tbsp peanut butter"}).json()
    pb = item(added, "peanut butter")
    assert pb["quantity"] == 2 and pb["unit"] == "tbsp" and pb["food"]["description"].startswith("Peanut butter")


def test_confirm_feeds_healthscore_and_awards_points(client, user, fake_db):
    meal = analyze(client, user, "2 slices of toast with peanut butter and a banana").json()
    res = client.post(f"/meals/{meal['meal_id']}/confirm")
    assert res.status_code == 200 and res.json()["status"] == "confirmed"
    stored = fake_db.tables["meal_entries"][meal["meal_id"]]
    assert stored["confirmed_at"]
    points = client.get(f"/gamification/{user}").json()
    assert points["total_points"] == 10                       # meal_logged
    again = client.post(f"/meals/{meal['meal_id']}/confirm")
    assert again.status_code == 409
    hs = client.get(f"/healthscore/{user}", params={"end_date": DAY}).json()
    assert hs["categories"]["nutrition"]["days_logged"] == 1  # confirmed meal counted


def test_estimated_and_discarded_meals_dont_count(client, user):
    keep = analyze(client, user, "a banana").json()
    toss = analyze(client, user, "a pizza").json()
    assert client.post(f"/meals/{toss['meal_id']}/discard").json()["status"] == "discarded"
    hs = client.get(f"/healthscore/{user}", params={"end_date": DAY}).json()
    assert hs["categories"]["nutrition"]["days_logged"] == 0
    assert client.patch(f"/meals/{toss['meal_id']}/items/{toss['items'][0]['meal_item_id']}", json={"quantity": 2}).status_code == 409
    assert keep["status"] == "estimated"


def test_list_meals_for_a_day(client, user):
    analyze(client, user, "a banana")
    analyze(client, user, "1 cup rice")
    meals = client.get("/meals", params={"user_id": user, "log_date": DAY}).json()
    assert len(meals) == 2
    client.post(f"/meals/{meals[0]['meal_id']}/discard")
    open_meals = client.get("/meals", params={"user_id": user, "log_date": DAY, "status": "estimated"}).json()
    assert [m["meal_id"] for m in open_meals] == [meals[1]["meal_id"]]


def test_food_search(client, user):
    res = client.get("/foods/search", params={"q": "pho"})
    assert res.status_code == 200 and res.json()
    assert client.get("/foods/search", params={"q": "xyzzy"}).json() == []


def test_nothing_recognised(client, user):
    res = analyze(client, user, "went for a run today")
    assert res.status_code == 422


def test_unknown_user(client, fake_fdc):
    assert analyze(client, str(uuid4()), "a banana").status_code == 404


def test_unknown_meal(client, fake_fdc):
    assert client.get(f"/meals/{uuid4()}").status_code == 404


@pytest.mark.parametrize("body", [
    {"text": "", "log_date": DAY},
    {"text": "x" * 501, "log_date": DAY},
    {"text": "a banana", "log_date": "yesterday"},
    {"text": "a banana", "log_date": DAY, "meal_type": "elevenses"},
])
def test_analyze_validation(client, user, body):
    assert client.post(f"/meals/{user}/analyze", json=body).status_code == 422


def test_bad_item_update(client, user):
    meal = analyze(client, user, "a banana").json()
    url = f"/meals/{meal['meal_id']}/items/{meal['items'][0]['meal_item_id']}"
    assert client.patch(url, json={"quantity": -1}).status_code == 422
    assert client.patch(url, json={"unit": "bucket"}).status_code == 422


def test_missing_fdc_key_is_a_clear_error(client, user, monkeypatch):
    from app.main import app
    from app.routers import meals
    app.dependency_overrides.pop(meals.get_fdc, None)
    meals._fdc_client.cache_clear()
    monkeypatch.delenv("FDC_API_KEY", raising=False)
    res = analyze(client, user, "a banana")
    assert res.status_code == 503 and "FDC_API_KEY" in res.json()["detail"]
