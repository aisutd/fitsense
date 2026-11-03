"""Supabase reads for the HealthScore: users' logs, goals and weights, then scoring in memory.

One user (the HealthScore endpoint) or everyone at once (league standings, forecasts): the same
data is loaded with a handful of queries and scored by the pure functions in app.healthscore.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException
from supabase import Client

from app import healthscore as hs

# range key -> (days back from end_date to the window's last day, window length)
RANGE_WINDOWS = {"day": (0, 1), "week": (0, 7), "last-week": (7, 7), "month": (0, 30)}

NOT_EXPECTED = ("rest_day", "before_signup")   # workout reasons that don't make a day's score provisional

PAGE = 1000   # PostgREST returns at most this many rows per request by default

# table -> (date column, columns, extra filters)
LOG_TABLES = {
    "workout_logs": ("workout_date", "user_id, workout_date, completion_status", {}),
    "meal_entries": ("log_date", "user_id, log_date, calories, protein_g, carbs_g, fat_g", {"status": "confirmed"}),
    "sleep_logs": ("sleep_date", "user_id, sleep_date, hours_slept, sleep_quality", {}),
    "activity_logs": ("log_date", "user_id, log_date, steps, active_minutes", {}),
}


def window(range_key: str, end_date: date) -> tuple[date, date, int]:
    offset, days = RANGE_WINDOWS[range_key]
    end = end_date - timedelta(days=offset)
    return end - timedelta(days=days - 1), end, days


def week_monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _first(response) -> dict | None:
    return response.data[0] if response.data else None


def _num(value) -> float | None:
    """Supabase returns numeric columns as numbers or strings depending on precision."""
    return float(value) if value is not None else None


def _day(value) -> date:
    return date.fromisoformat(str(value)[:10])


def all_rows(make_query) -> list[dict]:
    """Every row of a query, a page at a time (a bulk read can be over PostgREST's row limit)."""
    rows: list[dict] = []
    while True:
        page = make_query().range(len(rows), len(rows) + PAGE - 1).execute().data
        rows.extend(page)
        if len(page) < PAGE:
            return rows


def _select(supabase: Client, table: str, columns: str, user_id: str | None, **filters) -> list[dict]:
    def query():
        q = supabase.table(table).select(columns)
        if user_id is not None:
            q = q.eq("user_id", user_id)
        for column, value in filters.items():
            q = q.eq(column, value)
        return q.order(columns.split(",")[0].strip())
    return all_rows(query)


# --- users' settings -------------------------------------------------------------------

@dataclass
class UserContext:
    profile: dict
    goals: dict
    days_per_week: int | None


def get_profile(supabase: Client, user_id: str) -> dict:
    profile = _first(supabase.table("profiles").select("*").eq("user_id", user_id).limit(1).execute())
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _newest_by_user(rows: list[dict], order_col: str = "created_at") -> dict[str, dict]:
    newest: dict[str, dict] = {}
    for row in rows:
        current = newest.get(row["user_id"])
        if current is None or str(row.get(order_col) or "") > str(current.get(order_col) or ""):
            newest[row["user_id"]] = row
    return newest


def load_contexts(supabase: Client, user_id: str | None = None) -> dict[str, UserContext]:
    """Profile, active goals and planned workout days for one user (or everyone)."""
    if user_id is not None:
        profiles = [get_profile(supabase, user_id)]
    else:
        profiles = _select(supabase, "profiles", "user_id, created_at, age, height_cm, weight_kg, fitness_goal, workout_frequency", None)
    plans = _newest_by_user(_select(supabase, "workout_plans", "user_id, created_at, days_per_week", user_id))
    prefs = {r["user_id"]: r for r in _select(supabase, "user_preferences", "user_id, workout_days_per_week", user_id)}
    nutrition = _newest_by_user(_select(supabase, "nutrition_goals", "user_id, created_at, daily_calorie_target, protein_target_g, carbs_target_g, fat_target_g", user_id))
    sleep = _newest_by_user(_select(supabase, "sleep_goals", "user_id, created_at, target_hours", user_id))
    progress = _select(supabase, "progress_goals", "user_id, created_at, goal_type, target_value", user_id, status="active")
    steps = _newest_by_user([r for r in progress if r["goal_type"] == "daily_steps"])
    minutes = _newest_by_user([r for r in progress if r["goal_type"] == "daily_active_minutes"])

    contexts = {}
    for profile in profiles:
        uid = profile["user_id"]
        days = ((plans.get(uid) or {}).get("days_per_week") or (prefs.get(uid) or {}).get("workout_days_per_week")
                or profile.get("workout_frequency"))
        contexts[uid] = UserContext(profile, _goals(profile, days, nutrition.get(uid), sleep.get(uid),
                                                    steps.get(uid), minutes.get(uid)), days)
    return contexts


def _goals(profile: dict, days_per_week: int | None, goal: dict | None, sleep: dict | None,
           steps: dict | None, minutes: dict | None) -> dict:
    """Active targets, falling back to defaults (sleep, activity) or a profile-based estimate (nutrition)."""
    if goal and goal.get("daily_calorie_target"):
        nutrition = hs.macro_targets(float(goal["daily_calorie_target"]), protein_g=_num(goal.get("protein_target_g")),
                                     carbs_g=_num(goal.get("carbs_target_g")), fat_g=_num(goal.get("fat_target_g")))
        estimated = False
    else:
        nutrition = hs.estimate_nutrition_targets(profile["age"], float(profile["height_cm"]), float(profile["weight_kg"]),
                                                  profile["fitness_goal"], days_per_week)
        estimated = True
    return {
        "nutrition": {k: round(v, 1) for k, v in nutrition.items()},
        "nutrition_estimated": estimated,
        "sleep_target_hours": _num(sleep["target_hours"]) if sleep else hs.DEFAULT_SLEEP_TARGET_HOURS,
        "daily_steps": int(_num(steps["target_value"])) if steps else hs.DEFAULT_STEPS_TARGET,
        "daily_active_minutes": int(_num(minutes["target_value"])) if minutes else hs.DEFAULT_ACTIVE_MINUTES_TARGET,
    }


def workout_days_per_week(supabase: Client, user_id: str, profile: dict) -> int | None:
    """From the newest workout plan, else the user's preferences, else onboarding."""
    return load_contexts(supabase, user_id)[user_id].days_per_week


def current_goals(supabase: Client, user_id: str, profile: dict) -> dict:
    return load_contexts(supabase, user_id)[user_id].goals


def active_weights(supabase: Client) -> tuple[dict, str | None]:
    """Newest health_score_config, or the spec's default weights."""
    config = _first(supabase.table("health_score_config").select("*").order("version", desc=True).limit(1).execute())
    if not config:
        return dict(hs.DEFAULT_WEIGHTS), None
    weights = {k: _num(config[f"{'workout' if k == 'workouts' else k}_weight"]) for k in hs.CATEGORIES}
    return weights, config["config_id"]


# --- logs ----------------------------------------------------------------------------

def load_logs(supabase: Client, start: date, end: date, user_id: str | None = None) -> dict[str, dict[str, list]]:
    """{user_id: {table: rows}} for logs dated start..end (one user, or everyone)."""
    logs: dict[str, dict[str, list]] = defaultdict(lambda: {t: [] for t in LOG_TABLES})
    for table, (date_col, columns, filters) in LOG_TABLES.items():
        def query(table=table, date_col=date_col, columns=columns, filters=filters):
            q = supabase.table(table).select(columns).gte(date_col, start.isoformat()).lte(date_col, end.isoformat())
            if user_id is not None:
                q = q.eq("user_id", user_id)
            for column, value in filters.items():
                q = q.eq(column, value)
            return q.order(date_col).order("user_id")
        for row in all_rows(query):
            logs[row["user_id"]][table].append(row)
    return logs


def fetch_window(range_key: str, end_date: date) -> tuple[date, date]:
    """Dates of logs needed to score a window. A day also needs the night before (sleep) and the
    week so far (whether a day without a workout was a rest day)."""
    start, end, _ = window(range_key, end_date)
    if range_key == "day":
        return min(week_monday(end), end - timedelta(days=1)), end
    return start, end


# --- scoring ---------------------------------------------------------------------------

def score(ctx: UserContext, logs: dict[str, list], weights: dict, start: date, end: date, day: bool = False) -> dict:
    """HealthScore for start..end from already-loaded logs. day=True scores the single day `end`."""
    goals = ctx.goals

    def dated(table, col, first, last):
        return [r for r in logs[table] if first <= _day(r[col]) <= last]

    if day:
        monday = week_monday(end)
        earlier = dated("workout_logs", "workout_date", monday, end - timedelta(days=1))
        done_earlier = sum(hs.STATUS_CREDIT.get(w["completion_status"], 0.0) for w in earlier)
        workouts = hs.score_workout_day(
            [w["completion_status"] for w in dated("workout_logs", "workout_date", end, end)],
            ctx.days_per_week, done_earlier, 7 - end.weekday(),
        )
        signed_up = ctx.profile.get("created_at")
        if workouts.details.get("status") == "missed" and signed_up and end < _day(signed_up):
            workouts = hs.CategoryResult(None, {**workouts.details, "status": None, "reason": "before_signup"})
        night = end - timedelta(days=1)   # the night you woke up from
        sleep_rows = dated("sleep_logs", "sleep_date", night, night)
    else:
        workouts = hs.score_workouts([w["completion_status"] for w in dated("workout_logs", "workout_date", start, end)],
                                     ctx.days_per_week, (end - start).days + 1)
        sleep_rows = dated("sleep_logs", "sleep_date", start, end)

    days = (end - start).days + 1
    results = {
        "workouts": workouts,
        "nutrition": hs.score_nutrition(daily_meal_totals(dated("meal_entries", "log_date", start, end)),
                                        goals["nutrition"], days, targets_estimated=goals["nutrition_estimated"]),
        "sleep": hs.score_sleep([_num(s["hours_slept"]) for s in sleep_rows if s.get("hours_slept") is not None],
                                goals["sleep_target_hours"]),
        "activity": hs.score_activity(dated("activity_logs", "log_date", start, end),
                                      goals["daily_steps"], goals["daily_active_minutes"]),
    }
    if day and sleep_rows:
        results["sleep"].details["night_of"] = (end - timedelta(days=1)).isoformat()
        quality = sleep_rows[0].get("sleep_quality")
        if quality is not None:
            results["sleep"].details["sleep_quality"] = quality
    result = hs.build_result(results, weights)
    if day and results["workouts"].details.get("reason") in NOT_EXPECTED:
        # a rest day isn't missing data: the day is complete without a workout
        result["provisional"] = 0 < len(result["available_categories"]) < len(hs.CATEGORIES) - 1
    return result


def calculate(supabase: Client, user_id: str, range_key: str, end_date: date) -> tuple[dict, str | None]:
    """HealthScore for one user and window. Returns (result, config_id)."""
    ctx = load_contexts(supabase, user_id)[user_id]
    start, end, days = window(range_key, end_date)
    first, last = fetch_window(range_key, end_date)
    logs = load_logs(supabase, first, last, user_id)[user_id]
    weights, config_id = active_weights(supabase)
    result = score(ctx, logs, weights, start, end, day=range_key == "day")
    result["range"] = {"key": range_key, "start": start, "end": end, "days": days}
    return result, config_id


def calculate_everyone(supabase: Client, start: date, end: date) -> dict[str, dict]:
    """HealthScore over start..end for every user, with a few bulk queries (league standings)."""
    contexts = load_contexts(supabase)
    logs = load_logs(supabase, start, end)
    weights, _ = active_weights(supabase)
    return {uid: {**score(ctx, logs[uid], weights, start, end), "logs": logs[uid]} for uid, ctx in contexts.items()}


def daily_meal_totals(meals: list[dict]) -> list[dict]:
    """Sum confirmed meals into one row per day."""
    days: dict[str, dict] = defaultdict(lambda: {k: 0.0 for k in hs.NUTRIENT_WEIGHTS})
    for meal in meals:
        day = days[str(meal["log_date"])[:10]]
        for k in hs.NUTRIENT_WEIGHTS:
            day[k] += _num(meal.get(k)) or 0.0
    return list(days.values())
