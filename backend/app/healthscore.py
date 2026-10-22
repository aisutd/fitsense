"""HealthScore calculation: four category scores (0-100) and a weighted overall score.

Pure functions only - no database access - so they can be reused by the API, by
batch jobs, and in tests. A category returns None when there isn't enough data;
the overall score is then calculated from the available categories only
(a "provisional" score), and is None when no category has data.

HealthScore is an experimental motivational wellness metric, not a medically
validated health assessment.
"""

from dataclasses import dataclass

CATEGORIES = ("workouts", "nutrition", "sleep", "activity")

# Initial project weights from the spec. The active weights come from the newest
# health_score_config row; these are the fallback.
DEFAULT_WEIGHTS = {"workouts": 0.30, "nutrition": 0.25, "sleep": 0.25, "activity": 0.20}

DEFAULT_SLEEP_TARGET_HOURS = 8.0
DEFAULT_STEPS_TARGET = 8000
DEFAULT_ACTIVE_MINUTES_TARGET = 30

# A partially completed workout counts as half of a completed one.
PARTIAL_WORKOUT_CREDIT = 0.5

# Nutrition needs at least this many days with confirmed meals in the window
# (or every day, for windows shorter than this) to be meaningful.
MIN_NUTRITION_DAYS = 3

# How much each nutrient counts toward a day's nutrition score.
NUTRIENT_WEIGHTS = {"calories": 0.40, "protein_g": 0.30, "carbs_g": 0.15, "fat_g": 0.15}

# Used to derive macro targets from a calorie target when none are set:
# carbs 50% and fat 30% of calories (middle of the usual recommended ranges).
CARBS_SHARE, FAT_SHARE = 0.50, 0.30
KCAL_PER_G = {"protein_g": 4, "carbs_g": 4, "fat_g": 9}


@dataclass
class CategoryResult:
    score: float | None
    details: dict

    @property
    def available(self) -> bool:
        return self.score is not None


def closeness(actual: float, target: float) -> float:
    """100 when actual == target, dropping linearly with relative distance (floored at 0).

    Over- and under-shooting are treated the same: 7 h against an 8 h target and
    9 h against 8 h both give 87.5.
    """
    if target <= 0:
        raise ValueError("target must be positive")
    return max(0.0, 100.0 - abs(actual - target) / target * 100.0)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


# --- 1. Workouts -------------------------------------------------------------

def scheduled_workouts(days_per_week: int, window_days: int) -> int:
    """Workouts planned in a window, from the plan's days per week (at least 1)."""
    return max(1, round(days_per_week * window_days / 7))


def workout_score(completed: float, scheduled: int) -> float:
    """Workout Score = completed / scheduled x 100, capped at 100 (3 of 4 -> 75)."""
    if scheduled <= 0:
        raise ValueError("scheduled must be positive")
    return min(100.0, completed / scheduled * 100.0)


def score_workouts(statuses: list[str], days_per_week: int | None, window_days: int) -> CategoryResult:
    """statuses: completion_status of each workout log in the window."""
    completed = statuses.count("completed") + PARTIAL_WORKOUT_CREDIT * statuses.count("partial")
    details = {"logged": len(statuses), "completed": completed}
    if not days_per_week:
        return CategoryResult(None, {**details, "reason": "no_workout_plan"})
    scheduled = scheduled_workouts(days_per_week, window_days)
    details["scheduled"] = scheduled
    if not statuses:
        return CategoryResult(None, {**details, "reason": "no_workouts_logged"})
    return CategoryResult(workout_score(completed, scheduled), details)


# --- 2. Nutrition ------------------------------------------------------------

def macro_targets(calories: float, protein_g: float | None = None,
                  carbs_g: float | None = None, fat_g: float | None = None) -> dict:
    """Fill in missing macro targets from the calorie target."""
    return {
        "calories": calories,
        "protein_g": protein_g if protein_g else calories * 0.20 / KCAL_PER_G["protein_g"],
        "carbs_g": carbs_g if carbs_g else calories * CARBS_SHARE / KCAL_PER_G["carbs_g"],
        "fat_g": fat_g if fat_g else calories * FAT_SHARE / KCAL_PER_G["fat_g"],
    }


def estimate_nutrition_targets(age: int, height_cm: float, weight_kg: float,
                               fitness_goal: str, workout_days_per_week: int | None) -> dict:
    """Rough daily targets for users who haven't set nutrition goals.

    Mifflin-St Jeor resting energy, using the midpoint of its male (+5) and female
    (-161) constants since sex isn't collected, times an activity factor from
    planned workout days, adjusted for the user's goal.
    """
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 78
    days = workout_days_per_week or 0
    factor = 1.375 if days <= 3 else 1.55 if days <= 5 else 1.725
    calories = bmr * factor + {"lose_weight": -500, "build_muscle": 300}.get(fitness_goal, 0)
    protein_per_kg = {"build_muscle": 1.8, "lose_weight": 1.6}.get(fitness_goal, 1.2)
    targets = macro_targets(round(calories), protein_g=round(weight_kg * protein_per_kg))
    return {k: round(v) for k, v in targets.items()}


def nutrition_day_score(day: dict, targets: dict) -> float:
    """How closely one day's totals match the targets, weighted by nutrient."""
    return sum(w * closeness(day.get(k) or 0, targets[k]) for k, w in NUTRIENT_WEIGHTS.items())


def score_nutrition(daily_totals: list[dict], targets: dict | None, window_days: int,
                    targets_estimated: bool = False) -> CategoryResult:
    """daily_totals: one dict per day with confirmed meals (calories, protein_g, carbs_g, fat_g).

    Values must come from the NLP + nutrition database pipeline (confirmed
    meal_entries), never from a language model's own estimate.
    """
    needed = min(MIN_NUTRITION_DAYS, window_days)
    details = {"days_logged": len(daily_totals), "days_needed": needed, "targets_estimated": targets_estimated}
    if not targets:
        return CategoryResult(None, {**details, "reason": "no_nutrition_targets"})
    details["targets"] = {k: round(v, 1) for k, v in targets.items()}
    if len(daily_totals) < needed:
        return CategoryResult(None, {**details, "reason": "not_enough_meals_logged"})
    details["average"] = {k: round(_mean([d.get(k) or 0 for d in daily_totals]), 1) for k in NUTRIENT_WEIGHTS}
    return CategoryResult(_mean([nutrition_day_score(d, targets) for d in daily_totals]), details)


# --- 3. Sleep ----------------------------------------------------------------

def sleep_score(hours: float, target_hours: float) -> float:
    """Closeness to the sleep target (7 h against 8 h -> 87.5)."""
    return closeness(hours, target_hours)


def score_sleep(hours_per_night: list[float], target_hours: float) -> CategoryResult:
    details = {"nights_logged": len(hours_per_night), "target_hours": target_hours}
    if not hours_per_night:
        return CategoryResult(None, {**details, "reason": "no_sleep_logged"})
    details["average_hours"] = round(_mean(hours_per_night), 2)
    return CategoryResult(_mean([sleep_score(h, target_hours) for h in hours_per_night]), details)


# --- 4. Activity -------------------------------------------------------------

def activity_score(actual: float, target: float) -> float:
    """Activity Score = min(100, actual / target x 100) (6,000 of 8,000 steps -> 75)."""
    if target <= 0:
        raise ValueError("target must be positive")
    return min(100.0, actual / target * 100.0)


def score_activity(days: list[dict], steps_target: float, minutes_target: float) -> CategoryResult:
    """days: activity logs in the window ({"steps": ..., "active_minutes": ...}).

    Steps are used when logged; otherwise active minutes.
    """
    scores, steps, minutes = [], [], []
    for d in days:
        if d.get("steps") is not None:
            steps.append(d["steps"])
            scores.append(activity_score(d["steps"], steps_target))
        elif d.get("active_minutes") is not None:
            minutes.append(d["active_minutes"])
            scores.append(activity_score(d["active_minutes"], minutes_target))
    details = {"days_logged": len(scores), "steps_target": steps_target, "active_minutes_target": minutes_target}
    if not scores:
        return CategoryResult(None, {**details, "reason": "no_activity_logged"})
    if steps:
        details["average_steps"] = round(_mean(steps))
    if minutes:
        details["average_active_minutes"] = round(_mean(minutes))
    return CategoryResult(_mean(scores), details)


# --- 5. Overall --------------------------------------------------------------

def overall_score(scores: dict[str, float | None], weights: dict[str, float] = DEFAULT_WEIGHTS) -> float | None:
    """Weighted HealthScore over the categories that have a score.

    Missing categories are left out and the remaining weights re-scaled, so the
    result stays on 0-100. None when no category is available.
    """
    available = {k: s for k, s in scores.items() if s is not None and weights.get(k, 0) > 0}
    if not available:
        return None
    total_weight = sum(weights[k] for k in available)
    return sum(weights[k] * s for k, s in available.items()) / total_weight


def build_result(results: dict[str, CategoryResult], weights: dict[str, float] = DEFAULT_WEIGHTS) -> dict:
    """Combine category results into the API response shape."""
    raw = {k: results[k].score for k in CATEGORIES}
    overall = overall_score(raw, weights)
    available = [k for k in CATEGORIES if raw[k] is not None]
    rounded = {k: (round(v) if v is not None else None) for k, v in raw.items()}
    return {
        "overall_score": round(overall) if overall is not None else None,
        **rounded,
        "provisional": 0 < len(available) < len(CATEGORIES),
        "available_categories": available,
        "weights": {k: weights[k] for k in CATEGORIES},
        "categories": {
            k: {"score": rounded[k], "available": raw[k] is not None, **results[k].details} for k in CATEGORIES
        },
    }
