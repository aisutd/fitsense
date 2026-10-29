import pytest

from app import healthscore as hs

# --- spec examples --------------------------------------------------------------

def test_spec_workout_example_3_of_4_is_75():
    assert hs.workout_score(3, 4) == 75


def test_spec_sleep_example_7_of_8_is_about_88():
    assert round(hs.sleep_score(7, 8)) == 88


def test_spec_activity_example_6000_of_8000_is_75():
    assert hs.activity_score(6000, 8000) == 75


def test_spec_overall_formula():
    scores = {"workouts": 90, "nutrition": 75, "sleep": 80, "activity": 85}
    expected = 90 * 0.30 + 75 * 0.25 + 80 * 0.25 + 85 * 0.20
    assert hs.overall_score(scores) == pytest.approx(expected)
    assert round(expected) == 83  # matches the spec's illustrative output


# --- category functions -------------------------------------------------------------

def test_scores_are_capped_at_100():
    assert hs.workout_score(6, 4) == 100
    assert hs.activity_score(20000, 8000) == 100


def test_closeness_is_symmetric_and_floored():
    assert hs.closeness(9, 8) == hs.closeness(7, 8) == 87.5
    assert hs.closeness(0, 8) == 0
    assert hs.closeness(30, 8) == 0


@pytest.mark.parametrize("fn, args", [(hs.workout_score, (1, 0)), (hs.activity_score, (1, 0)), (hs.closeness, (1, 0))])
def test_zero_targets_rejected(fn, args):
    with pytest.raises(ValueError):
        fn(*args)


@pytest.mark.parametrize("days_per_week, window, expected", [(4, 7, 4), (4, 30, 17), (3, 7, 3), (1, 1, 1), (7, 30, 30)])
def test_scheduled_workouts(days_per_week, window, expected):
    assert hs.scheduled_workouts(days_per_week, window) == expected


def test_score_workouts_partial_counts_half():
    result = hs.score_workouts(["completed", "completed", "partial", "skipped"], days_per_week=4, window_days=7)
    assert result.score == 62.5
    assert result.details["completed"] == 2.5 and result.details["scheduled"] == 4


def test_score_workouts_unavailable_without_plan_or_logs():
    assert hs.score_workouts(["completed"], None, 7).details["reason"] == "no_workout_plan"
    assert hs.score_workouts([], 4, 7).details["reason"] == "no_workouts_logged"
    assert not hs.score_workouts([], 4, 7).available


def test_all_skipped_scores_zero_not_unavailable():
    assert hs.score_workouts(["skipped", "skipped"], 4, 7).score == 0


def test_score_sleep_averages_nights():
    result = hs.score_sleep([8, 7, 9], 8)
    assert result.score == pytest.approx((100 + 87.5 + 87.5) / 3)
    assert result.details["average_hours"] == 8
    assert hs.score_sleep([], 8).score is None


def test_score_activity_prefers_steps_and_falls_back_to_minutes():
    result = hs.score_activity([{"steps": 6000}, {"steps": None, "active_minutes": 15}], 8000, 30)
    assert result.score == pytest.approx((75 + 50) / 2)
    assert result.details["average_steps"] == 6000 and result.details["average_active_minutes"] == 15
    assert hs.score_activity([{"steps": None, "active_minutes": None}], 8000, 30).score is None


# --- nutrition ----------------------------------------------------------------------

TARGETS = {"calories": 2000, "protein_g": 150, "carbs_g": 250, "fat_g": 67}


def test_nutrition_on_target_is_100():
    days = [dict(TARGETS)] * 3
    assert hs.score_nutrition(days, TARGETS, 7).score == pytest.approx(100)


def test_nutrition_day_score_weights_nutrients():
    # Calories 10% over (90), protein half (50), carbs and fat on target (100).
    day = {"calories": 2200, "protein_g": 75, "carbs_g": 250, "fat_g": 67}
    assert hs.nutrition_day_score(day, TARGETS) == pytest.approx(0.4 * 90 + 0.3 * 50 + 0.15 * 100 + 0.15 * 100)


def test_nutrition_needs_enough_logged_days():
    two_days = [dict(TARGETS)] * 2
    result = hs.score_nutrition(two_days, TARGETS, 7)
    assert result.score is None and result.details["reason"] == "not_enough_meals_logged"
    # A 1-day window only needs 1 day.
    assert hs.score_nutrition([dict(TARGETS)], TARGETS, 1).score == pytest.approx(100)


def test_macro_targets_derived_from_calories():
    t = hs.macro_targets(2000)
    assert t["carbs_g"] == pytest.approx(250) and t["fat_g"] == pytest.approx(2000 * 0.3 / 9)
    assert hs.macro_targets(2000, protein_g=160)["protein_g"] == 160


def test_estimated_targets_are_reasonable_and_follow_goal():
    cut = hs.estimate_nutrition_targets(25, 180, 80, "lose_weight", 4)
    bulk = hs.estimate_nutrition_targets(25, 180, 80, "build_muscle", 4)
    assert 1500 < cut["calories"] < bulk["calories"] < 3500
    assert bulk["protein_g"] == round(80 * 1.8)


# --- overall & missing data ------------------------------------------------------------

def test_overall_rescales_weights_when_categories_missing():
    scores = {"workouts": 80, "nutrition": None, "sleep": 60, "activity": None}
    assert hs.overall_score(scores) == pytest.approx((80 * 0.30 + 60 * 0.25) / 0.55)


def test_overall_none_when_no_data():
    assert hs.overall_score({k: None for k in hs.CATEGORIES}) is None


def test_overall_uses_custom_weights():
    scores = {"workouts": 100, "nutrition": 0, "sleep": 0, "activity": 0}
    assert hs.overall_score(scores, {"workouts": 1, "nutrition": 0, "sleep": 0, "activity": 0}) == 100


def test_build_result_shape():
    results = {
        "workouts": hs.CategoryResult(75.4, {"completed": 3}),
        "nutrition": hs.CategoryResult(None, {"reason": "not_enough_meals_logged"}),
        "sleep": hs.CategoryResult(87.5, {}),
        "activity": hs.CategoryResult(75.0, {}),
    }
    out = hs.build_result(results)
    assert out["workouts"] == 75 and out["nutrition"] is None and out["sleep"] == 88
    assert out["provisional"] is True
    assert out["available_categories"] == ["workouts", "sleep", "activity"]
    assert out["overall_score"] == round((75.4 * 0.3 + 87.5 * 0.25 + 75 * 0.2) / 0.75)
    assert out["categories"]["nutrition"] == {"score": None, "available": False, "reason": "not_enough_meals_logged"}


def test_build_result_not_provisional_when_complete_or_empty():
    full = {k: hs.CategoryResult(50, {}) for k in hs.CATEGORIES}
    empty = {k: hs.CategoryResult(None, {}) for k in hs.CATEGORIES}
    assert hs.build_result(full)["provisional"] is False
    assert hs.build_result(empty)["provisional"] is False
    assert hs.build_result(empty)["overall_score"] is None
