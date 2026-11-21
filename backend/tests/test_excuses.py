"""Excused skips (the equipment wasn't there, the player couldn't get to the gym) don't count as missed:
in the HealthScore (day and window), and in the workouts forecast."""

from datetime import date
from uuid import uuid4

from app import healthscore as hs

PROFILE = {"name": "P", "age": 25, "height_cm": 180.0, "weight_kg": 80.0, "fitness_goal": "general_fitness",
           "fitness_level": "intermediate", "workout_frequency": 3, "workout_location": "gym"}


# --- the scoring rules --------------------------------------------------------------------

def test_an_excused_day_is_like_a_rest_day():
    result = hs.score_workout_day([hs.EXCUSED], 3, 0, 4)
    assert result.score is None and result.details["reason"] == "excused"


def test_a_workout_done_anyway_counts_over_the_excuse():
    assert hs.score_workout_day([hs.EXCUSED, "completed"], 3, 0, 4).score == 100


def test_excused_days_earlier_in_the_week_dont_make_today_missed():
    # 3 a week, Friday (3 days left including today), nothing done: missed, unless 1 was excused
    assert hs.score_workout_day([], 3, 0, 3).details["status"] == "missed"
    assert hs.score_workout_day([], 3, 0, 3, excused_earlier_this_week=1).details["reason"] == "rest_day"


def test_excused_days_come_off_the_scheduled_workouts():
    plain = hs.score_workouts(["completed", "completed", "skipped"], 3, 7)
    excused = hs.score_workouts(["completed", "completed", hs.EXCUSED], 3, 7)
    assert round(plain.score) == 67 and excused.score == 100
    assert excused.details["excused"] == 1


def test_a_fully_excused_week_has_no_workout_score():
    result = hs.score_workouts([hs.EXCUSED] * 3, 3, 7)
    assert result.score is None and result.details["reason"] == "excused"


# --- through the API ------------------------------------------------------------------------

def test_an_excused_skip_is_saved_and_scored_as_excused(client, fake_db):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    day = "2026-11-18"
    body = {"workout_date": day, "completion_status": "skipped", "skip_reason": "location"}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 200
    score = client.get(f"/healthscore/{uid}?range=day&end_date={day}").json()
    assert score["categories"]["workouts"]["reason"] == "excused"


def test_a_skip_for_no_time_still_counts(client):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    day = "2026-11-18"
    body = {"workout_date": day, "completion_status": "skipped", "skip_reason": "no_time"}
    assert client.post(f"/logs/{uid}/workouts", json=body).status_code == 200
    score = client.get(f"/healthscore/{uid}?range=day&end_date={day}").json()
    assert score["categories"]["workouts"]["score"] == 0


# --- the workouts forecast ------------------------------------------------------------------

def test_an_excused_week_doesnt_read_as_a_decline():
    from app.plans import model_module
    pf = model_module("progress_forecast")   # at the repository root
    origin = date(2026, 11, 9)   # Monday of the last complete week
    week = [{"workout_date": "2026-11-10", "completion_status": "completed"},
            {"workout_date": "2026-11-12", "completion_status": "skipped", "skip_reason": "location"},
            {"workout_date": "2026-11-14", "completion_status": "skipped", "skip_reason": "no_time"}]
    points = dict(pf.weekly_workouts(week, date(2026, 11, 9), origin))
    assert points[0] == 2   # the completed one and the excused one; the no-time skip doesn't count
