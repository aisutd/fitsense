"""Supabase reads for the HealthScore: a user's logs, goals and weights for a date window."""

from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException
from supabase import Client

from app import healthscore as hs

# range key -> (days back from end_date to the window's last day, window length)
RANGE_WINDOWS = {"week": (0, 7), "last-week": (7, 7), "month": (0, 30)}


def window(range_key: str, end_date: date) -> tuple[date, date, int]:
    offset, days = RANGE_WINDOWS[range_key]
    end = end_date - timedelta(days=offset)
    return end - timedelta(days=days - 1), end, days


def _first(response) -> dict | None:
    return response.data[0] if response.data else None


def _newest(supabase: Client, table: str, user_id: str, order_col: str = "created_at", **filters) -> dict | None:
    query = supabase.table(table).select("*").eq("user_id", user_id)
    for column, value in filters.items():
        query = query.eq(column, value)
    return _first(query.order(order_col, desc=True).limit(1).execute())


def _in_window(supabase: Client, table: str, columns: str, user_id: str, date_col: str,
               start: date, end: date, **filters) -> list[dict]:
    query = (
        supabase.table(table).select(columns).eq("user_id", user_id)
        .gte(date_col, start.isoformat()).lte(date_col, end.isoformat())
    )
    for column, value in filters.items():
        query = query.eq(column, value)
    return query.execute().data


def get_profile(supabase: Client, user_id: str) -> dict:
    profile = _first(supabase.table("profiles").select("*").eq("user_id", user_id).limit(1).execute())
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def workout_days_per_week(supabase: Client, user_id: str, profile: dict) -> int | None:
    """From the newest workout plan, else the user's preferences, else onboarding."""
    plan = _newest(supabase, "workout_plans", user_id)
    if plan and plan.get("days_per_week"):
        return plan["days_per_week"]
    prefs = _first(supabase.table("user_preferences").select("workout_days_per_week")
                   .eq("user_id", user_id).limit(1).execute())
    if prefs and prefs.get("workout_days_per_week"):
        return prefs["workout_days_per_week"]
    return profile.get("workout_frequency")


def current_goals(supabase: Client, user_id: str, profile: dict) -> dict:
    """Active targets, falling back to defaults (sleep, activity) or a profile-based estimate (nutrition)."""
    goal = _newest(supabase, "nutrition_goals", user_id)
    if goal and goal.get("daily_calorie_target"):
        nutrition = hs.macro_targets(
            float(goal["daily_calorie_target"]),
            protein_g=_num(goal.get("protein_target_g")),
            carbs_g=_num(goal.get("carbs_target_g")),
            fat_g=_num(goal.get("fat_target_g")),
        )
        estimated = False
    else:
        nutrition = hs.estimate_nutrition_targets(
            profile["age"], float(profile["height_cm"]), float(profile["weight_kg"]),
            profile["fitness_goal"], workout_days_per_week(supabase, user_id, profile),
        )
        estimated = True

    sleep = _newest(supabase, "sleep_goals", user_id)
    steps = _newest(supabase, "progress_goals", user_id, goal_type="daily_steps", status="active")
    minutes = _newest(supabase, "progress_goals", user_id, goal_type="daily_active_minutes", status="active")
    return {
        "nutrition": {k: round(v, 1) for k, v in nutrition.items()},
        "nutrition_estimated": estimated,
        "sleep_target_hours": _num(sleep["target_hours"]) if sleep else hs.DEFAULT_SLEEP_TARGET_HOURS,
        "daily_steps": int(_num(steps["target_value"])) if steps else hs.DEFAULT_STEPS_TARGET,
        "daily_active_minutes": int(_num(minutes["target_value"])) if minutes else hs.DEFAULT_ACTIVE_MINUTES_TARGET,
    }


def active_weights(supabase: Client) -> tuple[dict, str | None]:
    """Newest health_score_config, or the spec's default weights."""
    config = _first(supabase.table("health_score_config").select("*").order("version", desc=True).limit(1).execute())
    if not config:
        return dict(hs.DEFAULT_WEIGHTS), None
    weights = {k: _num(config[f"{'workout' if k == 'workouts' else k}_weight"]) for k in hs.CATEGORIES}
    return weights, config["config_id"]


def calculate(supabase: Client, user_id: str, range_key: str, end_date: date) -> tuple[dict, str | None]:
    """Load everything for the window and return (result, config_id)."""
    profile = get_profile(supabase, user_id)
    start, end, days = window(range_key, end_date)
    goals = current_goals(supabase, user_id, profile)

    workouts = _in_window(supabase, "workout_logs", "completion_status", user_id, "workout_date", start, end)
    meals = _in_window(supabase, "meal_entries", "log_date, calories, protein_g, carbs_g, fat_g",
                       user_id, "log_date", start, end, status="confirmed")
    sleep = _in_window(supabase, "sleep_logs", "hours_slept", user_id, "sleep_date", start, end)
    activity = _in_window(supabase, "activity_logs", "steps, active_minutes", user_id, "log_date", start, end)

    results = {
        "workouts": hs.score_workouts(
            [w["completion_status"] for w in workouts],
            workout_days_per_week(supabase, user_id, profile), days,
        ),
        "nutrition": hs.score_nutrition(
            daily_meal_totals(meals), goals["nutrition"], days, targets_estimated=goals["nutrition_estimated"],
        ),
        "sleep": hs.score_sleep(
            [_num(s["hours_slept"]) for s in sleep if s.get("hours_slept") is not None], goals["sleep_target_hours"],
        ),
        "activity": hs.score_activity(activity, goals["daily_steps"], goals["daily_active_minutes"]),
    }
    weights, config_id = active_weights(supabase)
    result = hs.build_result(results, weights)
    result["range"] = {"key": range_key, "start": start, "end": end, "days": days}
    return result, config_id


def daily_meal_totals(meals: list[dict]) -> list[dict]:
    """Sum confirmed meals into one row per day."""
    days: dict[str, dict] = defaultdict(lambda: {k: 0.0 for k in hs.NUTRIENT_WEIGHTS})
    for meal in meals:
        day = days[meal["log_date"]]
        for k in hs.NUTRIENT_WEIGHTS:
            day[k] += _num(meal.get(k)) or 0.0
    return list(days.values())


def _num(value) -> float | None:
    """Supabase returns numeric columns as numbers or strings depending on precision."""
    return float(value) if value is not None else None
