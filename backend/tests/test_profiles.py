from uuid import uuid4

import pytest


SAMPLE = {
    "age": 21,
    "height_cm": 175.3,
    "weight_kg": 70.25,
    "fitness_goal": "build_muscle",
    "fitness_level": "beginner",
    "workout_frequency": 4,
    "workout_location": "gym",
    "workout_preferences": ["strength", "cardio", "strength"],
}


def test_save_then_get_round_trip(client, fake_db):
    user_id = str(uuid4())

    put = client.put(f"/profiles/{user_id}", json=SAMPLE)
    assert put.status_code == 200
    saved = put.json()
    assert saved["user_id"] == user_id
    assert saved["weight_kg"] == round(70.25, 1)  # rounded to 1 decimal to match numeric(5,1)
    assert saved["workout_preferences"] == ["strength", "cardio"]  # deduped

    stored = fake_db.tables["profiles"][user_id]
    assert stored["fitness_goal"] == "build_muscle"

    get = client.get(f"/profiles/{user_id}")
    assert get.status_code == 200
    assert get.json() == saved


def test_save_overwrites_existing(client):
    user_id = str(uuid4())
    first = client.put(f"/profiles/{user_id}", json=SAMPLE).json()

    updated = {**SAMPLE, "weight_kg": 68.0, "fitness_level": "intermediate"}
    second = client.put(f"/profiles/{user_id}", json=updated).json()

    assert second["weight_kg"] == 68.0
    assert second["fitness_level"] == "intermediate"
    assert second["created_at"] == first["created_at"]
    assert client.get(f"/profiles/{user_id}").json()["weight_kg"] == 68.0


def test_preferences_optional(client):
    body = {k: v for k, v in SAMPLE.items() if k != "workout_preferences"}
    res = client.put(f"/profiles/{uuid4()}", json=body)
    assert res.status_code == 200
    assert res.json()["workout_preferences"] == []


def test_get_unknown_returns_404(client):
    res = client.get(f"/profiles/{uuid4()}")
    assert res.status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"age": 12},
        {"age": 101},
        {"height_cm": 50},
        {"weight_kg": 500},
        {"workout_frequency": 0},
        {"workout_frequency": 8},
        {"fitness_goal": "get_huge"},
        {"fitness_level": "expert"},
        {"workout_location": "moon"},
        {"workout_preferences": ["swimming"]},
        {"age": "twenty"},
        {"unexpected_field": True},
    ],
)
def test_invalid_profile_rejected(client, fake_db, change):
    user_id = str(uuid4())
    res = client.put(f"/profiles/{user_id}", json={**SAMPLE, **change})
    assert res.status_code == 422
    assert user_id not in fake_db.tables.get("profiles", {})


@pytest.mark.parametrize("missing", list(SAMPLE.keys() - {"workout_preferences"}))
def test_missing_required_field_rejected(client, missing):
    body = {k: v for k, v in SAMPLE.items() if k != missing}
    res = client.put(f"/profiles/{uuid4()}", json=body)
    assert res.status_code == 422


def test_bad_uuid_rejected(client):
    assert client.put("/profiles/not-a-uuid", json=SAMPLE).status_code == 422
    assert client.get("/profiles/not-a-uuid").status_code == 422


def test_name_saved_and_trimmed(client):
    user_id = str(uuid4())
    res = client.put(f"/profiles/{user_id}", json={**SAMPLE, "name": "  Rahul  "})
    assert res.status_code == 200
    assert res.json()["name"] == "Rahul"
    assert client.get(f"/profiles/{user_id}").json()["name"] == "Rahul"


def test_name_optional(client):
    res = client.put(f"/profiles/{uuid4()}", json=SAMPLE)
    assert res.status_code == 200
    assert res.json()["name"] is None


def test_empty_name_rejected(client):
    assert client.put(f"/profiles/{uuid4()}", json={**SAMPLE, "name": "   "}).status_code == 422


def test_workout_fields_synced_to_user_preferences(client, fake_db):
    user_id = str(uuid4())
    client.put(f"/profiles/{user_id}", json=SAMPLE)
    prefs = fake_db.tables["user_preferences"][user_id]
    assert prefs["workout_days_per_week"] == 4
    assert prefs["workout_location"] == "gym"
    assert prefs["preferred_workout_types"] == ["strength", "cardio"]

    fake_db.tables["user_preferences"][user_id]["available_equipment"] = ["dumbbells"]
    client.put(f"/profiles/{user_id}", json={**SAMPLE, "workout_frequency": 6})
    prefs = fake_db.tables["user_preferences"][user_id]
    assert prefs["workout_days_per_week"] == 6
    assert prefs["available_equipment"] == ["dumbbells"]  # untouched by profile saves
