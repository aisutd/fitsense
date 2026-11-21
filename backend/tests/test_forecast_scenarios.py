from datetime import date

from app import healthscore as hs
from app.forecast_scenarios import workout_scenarios

TARGETS = [date(2026, 10, 18), date(2026, 11, 8), date(2027, 1, 3)]


def category(*values):
    return {"predictions": list(zip(TARGETS, values))}


def forecast(categories, pace=2.0):
    weights = dict(hs.DEFAULT_WEIGHTS)
    overall = [hs.overall_score({c: f["predictions"][i][1] for c, f in categories.items()}, weights) for i in range(3)]
    return {
        "health_score": {"categories": categories, "weights": weights, "predictions": list(zip(TARGETS, overall))},
        "workouts_per_week": {"predictions": [(t, pace) for t in TARGETS]},
    }


def test_more_workouts_raise_the_healthscore_up_to_the_plan():
    result = workout_scenarios(forecast({"workouts": category(50, 50, 50), "sleep": category(90, 90, 90),
                                         "activity": category(70, 70, 70)}), days_per_week=4)
    by_count = {o["workouts_per_week"]: o for o in result["options"]}
    assert sorted(by_count) == [0, 1, 2, 3, 4, 5]
    four_weeks = [by_count[k]["predictions"][1]["value"] for k in range(6)]
    assert four_weeks == sorted(four_weeks)
    assert by_count[4]["workout_score"] == 100 and four_weeks[4] == four_weeks[5]   # capped at the plan
    assert result["planned_per_week"] == 4 and result["scheduled_per_week"] == 4


def test_scenarios_use_the_healthscore_weights():
    result = workout_scenarios(forecast({"workouts": category(50, 50, 50), "sleep": category(80, 80, 80)}), 4)
    full = next(o for o in result["options"] if o["workouts_per_week"] == 4)
    expected = hs.overall_score({"workouts": 100, "sleep": 80}, hs.DEFAULT_WEIGHTS)
    assert full["predictions"][0]["value"] == round(expected, 1)


def test_pace_comes_from_the_workouts_forecast():
    result = workout_scenarios(forecast({"workouts": category(50, 50, 50)}, pace=2.4), 4)
    assert result["pace"]["workouts_per_week"] == 2.4
    assert result["pace"]["workout_score"] == 60.0   # 2.4 of 4


def test_workouts_can_be_added_when_not_logged_yet():
    result = workout_scenarios(forecast({"sleep": category(90, 90, 90)}), 3)
    zero, three = result["options"][0], result["options"][3]
    assert zero["predictions"][0]["value"] < 90 < three["predictions"][0]["value"] + 1e-9


def test_no_scenarios_without_a_forecast_or_a_plan():
    assert workout_scenarios({}, 4) is None
    assert workout_scenarios(forecast({"sleep": category(90, 90, 90)}), None) is None
