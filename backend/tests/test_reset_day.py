"""Undoing logging: reset a whole day (DELETE /logs/{user_id}/day/{date}) and remove one meal
(DELETE /meals/{meal_id})."""

from uuid import uuid4

import pytest

DAY, OTHER_DAY = "2026-11-25", "2026-11-24"
PROFILE = {
    "age": 21, "height_cm": 175.0, "weight_kg": 70.0, "fitness_goal": "general_fitness",
    "fitness_level": "beginner", "workout_frequency": 3, "workout_location": "gym",
}
MEAL = {"meal_type": "lunch", "display_name": "Chicken rice bowl", "calories": 720, "protein_g": 48,
        "carbs_g": 86, "fat_g": 18}


@pytest.fixture
def user(client):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


def log_day(client, uid, day):
    """A workout, steps, a meal and the night of sleep before `day`."""
    assert client.post(f"/logs/{uid}/workouts", json={"workout_date": day, "completion_status": "completed"}).status_code in (200, 201)
    assert client.put(f"/logs/{uid}/activity/{day}", json={"steps": 9000}).status_code in (200, 201)
    night = {"2026-11-25": "2026-11-24", "2026-11-24": "2026-11-23"}[day]
    assert client.put(f"/logs/{uid}/sleep/{night}", json={"hours_slept": 7.5, "sleep_quality": 4}).status_code in (200, 201)
    res = client.post(f"/logs/{uid}/meals", json={**MEAL, "log_date": day})
    assert res.status_code in (200, 201), res.text


def day_view(client, uid, day):
    res = client.get(f"/logs/{uid}/day/{day}")
    assert res.status_code == 200, res.text
    return res.json()


def test_reset_clears_the_day_and_only_that_day(client, user):
    log_day(client, user, OTHER_DAY)
    log_day(client, user, DAY)
    before = day_view(client, user, DAY)
    assert before["workouts"] and before["sleep"] and before["activity"] and before["meals"]

    res = client.delete(f"/logs/{user}/day/{DAY}")
    assert res.status_code == 200, res.text
    assert res.json()["removed"] == {"workouts": 1, "sleep": 1, "activity": 1, "meals": 1}

    after = day_view(client, user, DAY)
    assert after["workouts"] == [] and after["sleep"] is None and after["activity"] is None and after["meals"] == []
    # the day before keeps its workout, steps and meal (its own night of sleep too)
    other = day_view(client, user, OTHER_DAY)
    assert other["workouts"] and other["activity"] and other["meals"] and other["sleep"]


def test_reset_with_nothing_logged(client, user):
    res = client.delete(f"/logs/{user}/day/{DAY}")
    assert res.status_code == 200
    assert res.json()["removed"] == {"workouts": 0, "sleep": 0, "activity": 0, "meals": 0}


def test_remove_one_logged_meal(client, user):
    client.post(f"/logs/{user}/meals", json={**MEAL, "log_date": DAY})
    client.post(f"/logs/{user}/meals", json={**MEAL, "display_name": "Tacos, 3", "log_date": DAY})
    meals = day_view(client, user, DAY)["meals"]
    assert len(meals) == 2
    tacos = next(m for m in meals if m["display_name"] == "Tacos, 3")

    res = client.delete(f"/meals/{tacos['meal_id']}?user_id={user}")
    assert res.status_code == 200, res.text
    assert [m["display_name"] for m in day_view(client, user, DAY)["meals"]] == ["Chicken rice bowl"]


def test_remove_meal_checks_the_owner(client, user):
    client.post(f"/logs/{user}/meals", json={**MEAL, "log_date": DAY})
    meal = day_view(client, user, DAY)["meals"][0]
    someone_else = str(uuid4())
    assert client.delete(f"/meals/{meal['meal_id']}?user_id={someone_else}").status_code == 404
    assert client.delete(f"/meals/{uuid4()}?user_id={user}").status_code == 404
    assert len(day_view(client, user, DAY)["meals"]) == 1
