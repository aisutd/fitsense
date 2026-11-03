"""The daily HealthScore: one day's logs (sleep = the night before), rest days vs missed workouts."""

from datetime import timedelta

import pytest

from app import healthscore as hs
from test_healthscore_api import TODAY, day, log_meal, log_sleep, log_steps, log_workout, make_user, score

# TODAY (2026-10-15) is a Thursday: Monday is day(3), Sunday is 3 days after TODAY.


@pytest.mark.parametrize("statuses, score_", [(["completed"], 100), (["partial"], 50), (["skipped"], 0),
                                              (["skipped", "completed"], 100)])
def test_logged_workout_day(statuses, score_):
    assert hs.score_workout_day(statuses, 4, 0, 4).score == score_


def test_day_without_a_workout_is_a_rest_day_while_the_plan_is_still_possible():
    # Thursday, 4 a week, 1 done: 3 still needed, Fri-Sun = 3 days left after today -> rest day
    result = hs.score_workout_day([], 4, 1, 4)
    assert result.score is None and result.details["reason"] == "rest_day"


def test_day_without_a_workout_is_missed_when_the_plan_no_longer_fits():
    # Thursday, 4 a week, nothing done: 4 needed but only 3 days left after today
    result = hs.score_workout_day([], 4, 0, 4)
    assert result.score == 0 and result.details["status"] == "missed"


def test_every_day_counts_on_a_seven_day_plan():
    assert hs.score_workout_day([], 7, 0, 7).score == 0


def test_daily_score_is_the_default_and_uses_only_that_day(client):
    uid = make_user(client)
    log_steps(client, uid, 0, 6000)          # today: 75
    log_steps(client, uid, 1, 8000)          # yesterday: not counted
    log_meal(client, uid, 0)
    res = client.get(f"/healthscore/{uid}", params={"end_date": TODAY.isoformat()}).json()
    assert res["range"] == {"key": "day", "start": day(0), "end": day(0), "days": 1}
    assert res["activity"] == 75 and res["categories"]["nutrition"]["days_logged"] == 1


def test_daily_sleep_is_the_night_before(client):
    uid = make_user(client)
    log_sleep(client, uid, 1, 6)             # night of yesterday -> today's sleep
    log_sleep(client, uid, 0, 8)             # tonight -> tomorrow's sleep
    today = score(client, uid, "day")
    assert today["sleep"] == 75 and today["categories"]["sleep"]["night_of"] == day(1)
    tomorrow = score(client, uid, "day", TODAY + timedelta(days=1))
    assert tomorrow["sleep"] == 100


def test_daily_workouts_rest_day_and_missed(client):
    uid = make_user(client, workout_frequency=4)
    log_workout(client, uid, 3)              # Monday
    log_workout(client, uid, 1, "partial")   # Wednesday
    assert score(client, uid, "day", TODAY - timedelta(days=1))["workouts"] == 50
    # Thursday, nothing logged: 1.5 done, 2.5 still needed, 3 days left after today -> rest day
    rest = score(client, uid, "day")
    assert rest["workouts"] is None and rest["categories"]["workouts"]["reason"] == "rest_day"
    # Friday, still nothing: 2.5 needed, only 2 days left after Friday -> missed
    assert score(client, uid, "day", TODAY + timedelta(days=1))["workouts"] == 0


def test_days_before_signing_up_have_no_score(client, fake_db):
    uid = make_user(client)
    fake_db.tables["profiles"][uid]["created_at"] = TODAY.isoformat()
    assert score(client, uid, "day", TODAY - timedelta(days=1))["overall_score"] is None
    # from sign-up on, a needed workout that wasn't done counts (Thursday: 4 needed, 3 days left)
    assert score(client, uid, "day")["workouts"] == 0


def test_day_log_lists_what_was_logged(client):
    uid = make_user(client)
    log_workout(client, uid, 0)
    log_sleep(client, uid, 1, 7.5)
    log_steps(client, uid, 0, 9000)
    log_meal(client, uid, 0, calories=650)
    log_meal(client, uid, 1)                  # another day
    got = client.get(f"/logs/{uid}/day/{day(0)}").json()
    assert got["date"] == day(0) and got["sleep"]["hours_slept"] == 7.5
    assert [w["completion_status"] for w in got["workouts"]] == ["completed"]
    assert got["activity"]["steps"] == 9000 and [m["calories"] for m in got["meals"]] == [650]


def test_a_rest_day_does_not_make_the_score_provisional(client):
    uid = make_user(client, workout_frequency=2)
    log_steps(client, uid, 0, 8000)
    log_sleep(client, uid, 1, 8)
    log_meal(client, uid, 0)
    res = score(client, uid, "day")
    assert res["workouts"] is None and res["provisional"] is False and res["overall_score"] is not None
