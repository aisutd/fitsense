"""Workout logs count toward the week's workout plan (so the weekly plan model can adapt)."""

from datetime import date
from uuid import uuid4

from app.plans import link_logs

MONDAY = date(2026, 10, 26)
PROFILE = {"name": "P", "age": 25, "height_cm": 180.0, "weight_kg": 80.0, "fitness_goal": "general_fitness",
           "fitness_level": "intermediate", "workout_frequency": 3, "workout_location": "gym"}


def log(day, status="completed", plan_id=None, day_number=None):
    return {"workout_log_id": str(uuid4()), "workout_date": day, "completion_status": status,
            "plan_id": plan_id, "day_number": day_number}


def test_unlinked_logs_fill_that_weeks_open_plan_days_in_date_order():
    saved = [("p1", {"week_start": MONDAY, "days": 2})]
    logs = [log("2026-10-29"), log("2026-10-27", plan_id="p1", day_number=1), log("2026-10-28"),
            log("2026-11-03"), log("2026-10-30")]
    linked = {l["workout_date"]: (l["plan_id"], l["day_number"]) for l in link_logs(saved, logs)}
    assert linked["2026-10-27"] == ("p1", 1)          # already linked
    assert linked["2026-10-28"] == ("p1", 2)          # first open day
    assert linked["2026-10-29"] == (None, None)       # plan is full
    assert linked["2026-11-03"] == (None, None)       # a week without a plan


def test_a_logged_workout_is_linked_to_the_weeks_plan(client, fake_db):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    plan_id = str(uuid4())
    fake_db.tables.setdefault("workout_plans", {})[plan_id] = {
        "plan_id": plan_id, "user_id": uid, "week_start": MONDAY.isoformat(), "days_per_week": 2,
        "created_at": "2026-10-26T00:00:00+00:00"}
    days = []
    for day in ("2026-10-27", "2026-10-29", "2026-10-31"):
        saved = client.post(f"/logs/{uid}/workouts", json={"workout_date": day, "completion_status": "completed"}).json()
        days.append((saved["plan_id"], saved["day_number"]))
    assert days == [(plan_id, 1), (plan_id, 2), (None, None)]
    # outside the plan's week: not linked
    other = client.post(f"/logs/{uid}/workouts", json={"workout_date": "2026-11-05", "completion_status": "completed"}).json()
    assert other["plan_id"] is None


def test_an_explicit_plan_day_is_kept(client, fake_db):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    plan_id = str(uuid4())
    body = {"workout_date": "2026-10-27", "completion_status": "partial", "plan_id": plan_id, "day_number": 3}
    saved = client.post(f"/logs/{uid}/workouts", json=body).json()
    assert (saved["plan_id"], saved["day_number"]) == (plan_id, 3)


def test_day_number_must_be_a_weekday_number(client):
    uid = str(uuid4())
    body = {"workout_date": "2026-10-27", "day_number": 8}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 422
