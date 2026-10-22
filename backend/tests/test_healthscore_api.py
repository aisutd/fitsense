from datetime import date, timedelta
from uuid import uuid4

import pytest

TODAY = date(2026, 10, 15)

PROFILE = {
    "name": "Sample",
    "age": 25,
    "height_cm": 180.0,
    "weight_kg": 80.0,
    "fitness_goal": "general_fitness",
    "fitness_level": "intermediate",
    "workout_frequency": 4,
    "workout_location": "gym",
}

NUTRITION_GOAL = {"daily_calorie_target": 2000, "protein_target_g": 150, "carbs_target_g": 250, "fat_target_g": 67}


def day(n: int) -> str:
    """n days before TODAY."""
    return (TODAY - timedelta(days=n)).isoformat()


def make_user(client, **profile) -> str:
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json={**PROFILE, **profile}).status_code == 200
    return uid


def score(client, uid, range_="week", end=TODAY):
    res = client.get(f"/healthscore/{uid}", params={"range": range_, "end_date": end.isoformat()})
    assert res.status_code == 200, res.text
    return res.json()


def log_workout(client, uid, n, status="completed"):
    res = client.post(f"/logs/{uid}/workouts", json={"workout_date": day(n), "completion_status": status})
    assert res.status_code == 200, res.text


def log_sleep(client, uid, n, hours):
    assert client.put(f"/logs/{uid}/sleep/{day(n)}", json={"hours_slept": hours}).status_code == 200


def log_steps(client, uid, n, steps):
    assert client.put(f"/logs/{uid}/activity/{day(n)}", json={"steps": steps}).status_code == 200


def log_meal(client, uid, n, **nutrition):
    body = {"log_date": day(n), "calories": 2000, "protein_g": 150, "carbs_g": 250, "fat_g": 67, **nutrition}
    assert client.post(f"/logs/{uid}/meals", json=body).status_code == 200


@pytest.fixture
def complete_user(client):
    """Logs everything: 3 of 4 workouts, 7 h sleep vs 8, 6,000 of 8,000 steps, on-target meals."""
    uid = make_user(client)
    assert client.put(f"/goals/{uid}", json={"nutrition": NUTRITION_GOAL, "sleep_target_hours": 8, "daily_steps": 8000}).status_code == 200
    for n in (0, 2, 4):
        log_workout(client, uid, n)
    for n in range(7):
        log_sleep(client, uid, n, 7)
        log_steps(client, uid, n, 6000)
    for n in range(3):
        log_meal(client, uid, n, calories=1200, protein_g=90, carbs_g=150, fat_g=40)
        log_meal(client, uid, n, calories=800, protein_g=60, carbs_g=100, fat_g=27)
    return uid


# --- sample users ---------------------------------------------------------------

def test_complete_user_matches_spec_examples(client, complete_user):
    out = score(client, complete_user)
    assert out["workouts"] == 75      # 3 of 4
    assert out["sleep"] == 88         # 7 h vs 8 h
    assert out["activity"] == 75      # 6,000 of 8,000 steps
    assert out["nutrition"] == 100    # two meals a day adding up to the targets
    assert out["overall_score"] == round(75 * 0.30 + 100 * 0.25 + 87.5 * 0.25 + 75 * 0.20)
    assert out["provisional"] is False
    assert out["available_categories"] == ["workouts", "nutrition", "sleep", "activity"]
    assert out["categories"]["workouts"]["scheduled"] == 4
    assert out["categories"]["sleep"]["average_hours"] == 7
    assert out["categories"]["activity"]["average_steps"] == 6000
    assert out["categories"]["nutrition"]["targets_estimated"] is False
    assert "not a medical" in out["disclaimer"]


def test_new_user_has_no_score(client):
    out = score(client, make_user(client))
    assert out["overall_score"] is None
    assert out["provisional"] is False
    assert all(out[k] is None for k in ("workouts", "nutrition", "sleep", "activity"))
    assert out["categories"]["workouts"]["reason"] == "no_workouts_logged"
    assert out["categories"]["nutrition"]["reason"] == "not_enough_meals_logged"


def test_sleep_only_user_gets_provisional_score(client):
    uid = make_user(client)
    log_sleep(client, uid, 1, 8)
    out = score(client, uid)
    assert out["overall_score"] == 100 and out["sleep"] == 100
    assert out["provisional"] is True
    assert out["available_categories"] == ["sleep"]


def test_overachiever_is_capped(client):
    uid = make_user(client, workout_frequency=2)
    for n in range(5):
        log_workout(client, uid, n)
        log_steps(client, uid, n, 20000)
    out = score(client, uid)
    assert out["workouts"] == 100 and out["activity"] == 100 and out["overall_score"] == 100


def test_struggling_user(client):
    uid = make_user(client)
    log_workout(client, uid, 1, "skipped")
    log_workout(client, uid, 3, "partial")
    log_sleep(client, uid, 1, 4)
    log_steps(client, uid, 1, 2000)
    out = score(client, uid)
    assert out["workouts"] == round(0.5 / 4 * 100)
    assert out["sleep"] == 50 and out["activity"] == 25
    assert out["nutrition"] is None and out["provisional"] is True


def test_users_do_not_see_each_others_data(client, complete_user):
    other = make_user(client)
    assert score(client, other)["overall_score"] is None
    assert score(client, complete_user)["overall_score"] is not None


# --- windows, goals, weights ---------------------------------------------------------

def test_ranges_select_the_right_days(client):
    uid = make_user(client)
    log_sleep(client, uid, 0, 8)    # this week
    log_sleep(client, uid, 10, 4)   # last week
    log_sleep(client, uid, 20, 6)   # earlier this month
    assert score(client, uid, "week")["sleep"] == 100
    assert score(client, uid, "last-week")["sleep"] == 50
    month = score(client, uid, "month")
    assert month["categories"]["sleep"]["nights_logged"] == 3
    assert month["range"] == {"key": "month", "start": day(29), "end": day(0), "days": 30}


def test_end_date_moves_the_window(client):
    uid = make_user(client)
    log_sleep(client, uid, 0, 8)
    assert score(client, uid, end=TODAY - timedelta(days=1))["sleep"] is None


def test_month_scales_scheduled_workouts(client):
    uid = make_user(client)
    log_workout(client, uid, 0)
    assert score(client, uid, "month")["categories"]["workouts"]["scheduled"] == 17


def test_workout_plan_overrides_onboarding_days(client, fake_db):
    uid = make_user(client)
    fake_db.table("workout_plans").insert({"user_id": uid, "plan_name": "PPL", "days_per_week": 2}).execute()
    log_workout(client, uid, 0)
    assert score(client, uid)["workouts"] == 50


def test_nutrition_targets_estimated_without_goal(client):
    uid = make_user(client)
    goals = client.get(f"/goals/{uid}").json()
    assert goals["nutrition_estimated"] is True
    assert 1500 < goals["nutrition"]["calories"] < 3500
    assert goals["sleep_target_hours"] == 8 and goals["daily_steps"] == 8000


def test_newest_goal_wins(client):
    uid = make_user(client)
    client.put(f"/goals/{uid}", json={"sleep_target_hours": 8, "daily_steps": 8000})
    goals = client.put(f"/goals/{uid}", json={"sleep_target_hours": 7, "daily_steps": 10000}).json()
    assert goals["sleep_target_hours"] == 7 and goals["daily_steps"] == 10000
    log_sleep(client, uid, 0, 7)
    assert score(client, uid)["sleep"] == 100


def test_unconfirmed_meals_ignored(client, fake_db):
    uid = make_user(client)
    client.put(f"/goals/{uid}", json={"nutrition": NUTRITION_GOAL})
    for n in range(3):
        fake_db.table("meal_entries").insert(
            {"user_id": uid, "log_date": day(n), "status": "estimated", "calories": 2000,
             "protein_g": 150, "carbs_g": 250, "fat_g": 67}
        ).execute()
    assert score(client, uid)["nutrition"] is None


def test_weights_from_config(client, fake_db, complete_user):
    fake_db.table("health_score_config").insert(
        {"version": 2, "workout_weight": 1.0, "nutrition_weight": 0, "sleep_weight": 0, "activity_weight": 0}
    ).execute()
    out = score(client, complete_user)
    assert out["weights"]["workouts"] == 1.0
    assert out["overall_score"] == out["workouts"] == 75


# --- snapshots ----------------------------------------------------------------------

def test_snapshot_saved_and_listed(client, complete_user, fake_db):
    res = client.post(f"/healthscore/{complete_user}/snapshots", params={"end_date": TODAY.isoformat()})
    assert res.status_code == 200
    snap = res.json()
    stored = fake_db.tables["health_scores"][snap["score_id"]]
    assert stored["score"] == snap["overall_score"] and stored["workout_score"] == 75
    assert stored["range_end"] == day(0) and stored["provisional"] is False
    history = client.get(f"/healthscore/{complete_user}/history").json()
    assert len(history) == 1 and history[0]["score_id"] == snap["score_id"]


# --- validation & errors ----------------------------------------------------------------

def test_unknown_user_404(client):
    missing = str(uuid4())
    assert client.get(f"/healthscore/{missing}").status_code == 404
    assert client.get(f"/goals/{missing}").status_code == 404
    assert client.post(f"/logs/{missing}/workouts", json={"workout_date": day(0)}).status_code == 404
    assert client.put(f"/logs/{missing}/sleep/{day(0)}", json={"hours_slept": 8}).status_code == 404


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("put", "/logs/{uid}/sleep/2026-10-15", {"hours_slept": 25}),
        ("put", "/logs/{uid}/sleep/not-a-date", {"hours_slept": 8}),
        ("put", "/logs/{uid}/activity/2026-10-15", {}),
        ("put", "/logs/{uid}/activity/2026-10-15", {"steps": -1}),
        ("post", "/logs/{uid}/workouts", {"workout_date": "2026-10-15", "completion_status": "maybe"}),
        ("post", "/logs/{uid}/meals", {"log_date": "2026-10-15", "calories": 500}),
        ("post", "/logs/{uid}/meals", {"log_date": "2026-10-15", "calories": -1, "protein_g": 1, "carbs_g": 1, "fat_g": 1}),
        ("put", "/goals/{uid}", {"sleep_target_hours": 30}),
        ("put", "/goals/{uid}", {"nutrition": {"daily_calorie_target": 100}}),
    ],
)
def test_invalid_input_rejected(client, method, path, body):
    uid = make_user(client)
    assert getattr(client, method)(path.format(uid=uid), json=body).status_code == 422


def test_invalid_range_rejected(client):
    uid = make_user(client)
    assert client.get(f"/healthscore/{uid}", params={"range": "year"}).status_code == 422


def test_sleep_log_replaces_same_night(client):
    uid = make_user(client)
    log_sleep(client, uid, 0, 5)
    log_sleep(client, uid, 0, 8)
    out = score(client, uid)
    assert out["categories"]["sleep"]["nights_logged"] == 1 and out["sleep"] == 100
