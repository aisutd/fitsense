"""Skip reasons, swapped days and same-day swap requests (backend/sql/009_workout_log_swaps.sql).

The swap itself and the swap-aware weekly adaptation run in adaptive_week_two.py / weekly_plan.py
and are tested in test_adaptive_week_two.py at the repository root."""

from uuid import uuid4

PROFILE = {"name": "P", "age": 25, "height_cm": 180.0, "weight_kg": 80.0, "fitness_goal": "general_fitness",
           "fitness_level": "intermediate", "workout_frequency": 3, "workout_location": "gym"}


def make_user(client) -> str:
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


def saved_logs(fake_db, uid):
    return [r for r in fake_db.tables.get("workout_logs", {}).values() if r["user_id"] == uid]


def test_a_skip_reason_is_saved_with_a_skipped_workout(client, fake_db):
    uid = make_user(client)
    body = {"workout_date": "2026-10-27", "completion_status": "skipped", "skip_reason": "no_equipment"}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 200
    assert saved_logs(fake_db, uid)[0]["skip_reason"] == "no_equipment"


def test_a_swapped_day_is_saved(client, fake_db):
    uid = make_user(client)
    body = {"workout_date": "2026-10-27", "completion_status": "completed", "swapped": True}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 200
    assert saved_logs(fake_db, uid)[0]["swapped"] is True


def test_plain_logs_send_no_new_columns(client, fake_db):
    """Logging keeps working before 009 has been run: the new columns are only sent when used."""
    uid = make_user(client)
    assert client.post(f"/logs/{uid}/workouts", json={"workout_date": "2026-10-27"}).status_code == 200
    row = saved_logs(fake_db, uid)[0]
    assert "skip_reason" not in row and "swapped" not in row


def test_a_skip_reason_needs_a_skipped_workout(client):
    uid = make_user(client)
    body = {"workout_date": "2026-10-27", "completion_status": "completed", "skip_reason": "no_equipment"}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 422


def test_unknown_skip_reasons_are_rejected(client):
    uid = make_user(client)
    body = {"workout_date": "2026-10-27", "completion_status": "skipped", "skip_reason": "tired"}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 422


def test_a_swap_has_to_say_what_changed(client):
    uid = make_user(client)
    assert client.post(f"/plans/{uid}/swap", json={"day": 1}).status_code == 422
    assert client.post(f"/plans/{uid}/swap", json={"day": 8, "without": ["barbell"]}).status_code == 422
    assert client.post(f"/plans/{uid}/swap", json={"day": 1, "location": "space"}).status_code == 422
