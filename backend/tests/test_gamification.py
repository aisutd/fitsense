from uuid import uuid4

import pytest

from app.gamification import LEVEL_THRESHOLDS, MAX_LEVEL, POINTS, PointAction, level_for, level_progress

PROFILE = {
    "age": 21,
    "height_cm": 175.0,
    "weight_kg": 70.0,
    "fitness_goal": "build_muscle",
    "fitness_level": "beginner",
    "workout_frequency": 4,
    "workout_location": "gym",
}


@pytest.fixture
def user_id(client):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


def award(client, user_id, action, source_id=None):
    body = {"action": action} if source_id is None else {"action": action, "source_id": source_id}
    return client.post(f"/gamification/{user_id}/points", json=body)


# --- level math -------------------------------------------------------------

@pytest.mark.parametrize(
    "points, level",
    [(0, 1), (199, 1), (200, 2), (250, 2), (499, 2), (500, 3), (9999, 9), (10000, 10), (999999, 10), (-5, 1)],
)
def test_level_for(points, level):
    assert level_for(points) == level


def test_thresholds_start_at_zero_and_ascend():
    assert LEVEL_THRESHOLDS[0] == 0
    assert LEVEL_THRESHOLDS == sorted(set(LEVEL_THRESHOLDS))


def test_every_action_has_positive_points():
    assert set(POINTS) == set(PointAction)
    assert all(p > 0 for p in POINTS.values())


def test_level_progress_mid_level():
    assert level_progress(250) == {
        "level": 2,
        "current_level_points": 200,
        "next_level_points": 500,
        "points_to_next_level": 250,
        "progress_percent": 16.7,
    }


def test_level_progress_max_level():
    p = level_progress(LEVEL_THRESHOLDS[-1] + 123)
    assert p["level"] == MAX_LEVEL
    assert p["next_level_points"] is None and p["points_to_next_level"] is None
    assert p["progress_percent"] == 100.0


# --- endpoints --------------------------------------------------------------

def test_new_user_starts_at_zero(client, user_id):
    res = client.get(f"/gamification/{user_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["total_points"] == 0 and body["level"] == 1
    assert body["points_to_next_level"] == 200


def test_task_example_workout_takes_200_to_250_level_2(client, user_id, fake_db):
    # Get to 200 points: onboarding (100) + 2 workouts (50 each).
    award(client, user_id, "onboarding_completed")
    award(client, user_id, "workout_completed", "w1")
    award(client, user_id, "workout_completed", "w2")
    assert client.get(f"/gamification/{user_id}").json()["total_points"] == 200

    res = award(client, user_id, "workout_completed", "w3")
    assert res.status_code == 200
    body = res.json()
    assert body["points_awarded"] == 50
    assert body["total_points"] == 250
    assert body["level"] == 2
    assert body["awarded"] is True

    stored = fake_db.tables["user_gamification"][user_id]
    assert stored["total_xp"] == 250 and stored["level"] == 2
    assert client.get(f"/gamification/{user_id}").json()["level"] == 2


def test_level_up_flag(client, user_id):
    award(client, user_id, "onboarding_completed")  # 100
    res = award(client, user_id, "onboarding_completed").json()  # 200 -> level 2
    assert res["previous_level"] == 1 and res["level"] == 2 and res["leveled_up"] is True
    res = award(client, user_id, "meal_logged").json()  # 210, still level 2
    assert res["leveled_up"] is False


def test_same_source_only_rewarded_once(client, user_id):
    first = award(client, user_id, "workout_completed", "log-1").json()
    again = award(client, user_id, "workout_completed", "log-1").json()
    assert first["total_points"] == 50
    assert again["awarded"] is False and again["points_awarded"] == 0 and again["total_points"] == 50
    # A different action with the same source id still counts.
    other = award(client, user_id, "sleep_logged", "log-1").json()
    assert other["awarded"] is True and other["total_points"] == 60


def test_no_source_id_always_rewarded(client, user_id):
    award(client, user_id, "meal_logged")
    res = award(client, user_id, "meal_logged").json()
    assert res["total_points"] == 20


def test_history_newest_first(client, user_id):
    award(client, user_id, "onboarding_completed")
    award(client, user_id, "workout_completed", "w1")
    res = client.get(f"/gamification/{user_id}/history")
    assert res.status_code == 200
    events = res.json()
    assert [e["action"] for e in events] == ["workout_completed", "onboarding_completed"]
    assert events[0]["points"] == 50 and events[0]["source_id"] == "w1"
    assert len(client.get(f"/gamification/{user_id}/history?limit=1").json()) == 1


def test_unknown_user_returns_404(client):
    missing = str(uuid4())
    assert client.get(f"/gamification/{missing}").status_code == 404
    assert award(client, missing, "workout_completed").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"action": "hacked_points"},
        {"action": "workout_completed", "points": 1000000},
        {"action": "workout_completed", "source_id": ""},
        {"action": "workout_completed", "source_id": "x" * 101},
    ],
)
def test_invalid_award_rejected(client, user_id, body):
    assert client.post(f"/gamification/{user_id}/points", json=body).status_code == 422
    assert client.get(f"/gamification/{user_id}").json()["total_points"] == 0


def test_bad_uuid_rejected(client):
    assert client.get("/gamification/not-a-uuid").status_code == 422
    assert award(client, "not-a-uuid", "workout_completed").status_code == 422


def test_history_limit_validated(client, user_id):
    assert client.get(f"/gamification/{user_id}/history?limit=0").status_code == 422
    assert client.get(f"/gamification/{user_id}/history?limit=101").status_code == 422


def test_actions_and_levels_listed(client):
    actions = client.get("/gamification/actions").json()
    assert {"action": "workout_completed", "points": 50} in actions
    assert len(actions) == len(POINTS)
    levels = client.get("/gamification/levels").json()
    assert levels[0] == {"level": 1, "min_points": 0}
    assert levels[1] == {"level": 2, "min_points": 200}
    assert len(levels) == MAX_LEVEL


# --- daily check-in streak (drives the reward effects) ----------------------

def test_checkin_streak_counts_any_log_and_survives_recovery_days(client, user_id):
    log = lambda path, method="put", **body: getattr(client, method)(f"/logs/{user_id}/{path}", json=body).json()
    assert log("activity/2026-10-26", steps=5000)["checkin_streak"] == 1
    # last night's sleep counts for the day you woke up (the 27th)
    assert log("sleep/2026-10-26", hours_slept=7.5, sleep_quality=4)["checkin_streak"] == 2
    # a recovery day with only steps keeps it going; a completed workout extends it
    assert log("activity/2026-10-28", steps=4000)["checkin_streak"] == 3
    assert log("workouts", "post", workout_date="2026-10-29", completion_status="completed")["checkin_streak"] == 4
    # a day with nothing logged breaks it
    assert log("activity/2026-10-31", steps=9000)["checkin_streak"] == 1


def test_seven_day_streak_reward_comes_from_the_checkin_streak(client, user_id, fake_db):
    # six days of steps (recovery days, no workouts), then a completed workout on day seven
    for day in range(20, 26):
        client.put(f"/logs/{user_id}/activity/2026-10-{day}", json={"steps": 3000})
    seventh = client.post(f"/logs/{user_id}/workouts", json={"workout_date": "2026-10-26", "completion_status": "completed"}).json()
    assert seventh["checkin_streak"] == 7
    workout_xp = POINTS[PointAction.workout_completed]
    assert seventh["rewards"]["points_awarded"] == workout_xp + POINTS[PointAction.streak_7_days]
    # logging something else for the same day doesn't pay the streak bonus twice
    client.put(f"/logs/{user_id}/sleep/2026-10-25", json={"hours_slept": 8})
    bonuses = [e for e in fake_db.tables["xp_events"].values() if e["action"] == PointAction.streak_7_days.value]
    assert [e["source_id"] for e in bonuses] == ["checkin:2026-10-26"]
    streaks = client.get(f"/gamification/{user_id}/avatars").json()["streaks"]
    assert streaks[0]["streak_type"] == "checkin"
