from datetime import date, timedelta
from uuid import uuid4

TODAY = date(2026, 10, 15)  # a Thursday; the last complete week starts Monday 2026-10-05

PROFILE = {
    "name": "Forecast", "age": 25, "height_cm": 180.0, "weight_kg": 80.0, "fitness_goal": "general_fitness",
    "fitness_level": "intermediate", "workout_frequency": 4, "workout_location": "gym",
}


def make_user(client) -> str:
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json=PROFILE).status_code == 200
    return uid


def monday(weeks_back: int) -> date:
    """Monday of the complete week weeks_back before the latest complete one."""
    return TODAY - timedelta(days=TODAY.weekday()) - timedelta(weeks=1 + weeks_back)


def log_week(client, uid, weeks_back, workouts, hours=7, steps=6000):
    start = monday(weeks_back)
    for i in range(workouts):
        res = client.post(f"/logs/{uid}/workouts",
                          json={"workout_date": (start + timedelta(days=i)).isoformat(), "completion_status": "completed"})
        assert res.status_code == 200, res.text
    for d in range(7):
        day = (start + timedelta(days=d)).isoformat()
        assert client.put(f"/logs/{uid}/sleep/{day}", json={"hours_slept": hours}).status_code == 200
        assert client.put(f"/logs/{uid}/activity/{day}", json={"steps": steps}).status_code == 200


def forecast(client, uid):
    res = client.get(f"/forecast/{uid}/healthscore", params={"end_date": TODAY.isoformat()})
    assert res.status_code == 200, res.text
    return res.json()


def test_new_user_has_no_forecast_yet(client):
    result = forecast(client, make_user(client))
    assert result["based_on"] == "none"
    assert result["trend"] is None and result["scenarios"] == []


def test_unknown_user_is_404(client):
    assert client.get(f"/forecast/{uuid4()}/healthscore").status_code == 404


def test_history_matches_the_healthscore_screen(client):
    uid = make_user(client)
    for weeks_back, workouts in ((2, 1), (1, 2), (0, 3)):
        log_week(client, uid, weeks_back, workouts)
    result = forecast(client, uid)
    assert result["based_on"] == "complete_weeks" and result["weeks_of_data"] == 3
    for week in result["history"]:
        end = date.fromisoformat(week["week_start"]) + timedelta(days=6)
        screen = client.get(f"/healthscore/{uid}", params={"range": "week", "end_date": end.isoformat()}).json()
        assert week["overall"] == screen["overall_score"]
        assert week["workouts"] == screen["workouts"]


def test_more_workouts_raise_the_forecast_up_to_the_plan(client):
    uid = make_user(client)
    for weeks_back in range(3):
        log_week(client, uid, weeks_back, 2)
    result = forecast(client, uid)
    by_count = {s["workouts_per_week"]: s for s in result["scenarios"]}
    four_weeks = [by_count[k]["predictions"][1]["value"] for k in sorted(by_count)]
    assert four_weeks == sorted(four_weeks)                       # every extra workout helps...
    assert by_count[4]["workout_score"] == 100                     # ...until the 4-day plan is met
    assert by_count[5]["predictions"][1]["value"] == by_count[4]["predictions"][1]["value"]
    assert result["pace"]["workouts_per_week"] == 2.0              # 2 a week, every week


def test_trend_follows_rising_workouts(client):
    uid = make_user(client)
    for weeks_back, workouts in ((3, 1), (2, 2), (1, 3), (0, 4)):
        log_week(client, uid, weeks_back, workouts)
    result = forecast(client, uid)
    assert result["trend"]["categories"]["workouts"]["slope"] > 0
    assert result["trend"]["predictions"][0]["value"] >= result["history"][0]["overall"]
