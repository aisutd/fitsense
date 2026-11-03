"""Weekly linear-regression forecasts of body weight, workouts, daily steps and HealthScore.

Each metric is averaged per week (Monday to Sunday, UTC) and fit with a weighted linear
regression on the user's own history. Two things make it adapt to the user:

- Recent weeks count more (WEEK_HALF_LIFE), and the forecast is refit every week from the
  weeks completed so far, so a change in habits shows up in the next forecast.
- The trend is pulled toward a prior from the user's profile: no change for workouts (their
  planned workout_frequency is the starting point), and the fitness_goal's expected rate for
  weight. With little history the prior dominates; as weeks accumulate the user's trend wins.

The weight forecast uses the workout forecast: the goal's expected weight change is scaled by
how much of their planned workouts the user is forecast to complete next week.

Three things keep the forecasts realistic:

- Damped trend (Holt): each week ahead keeps DAMPING of the previous week's trend, so a trend
  fitted on a few weeks levels off instead of running away over 12 weeks.
- Only full weeks count: the week a user joined (unless they joined on a Monday) and weeks with
  fewer than MIN_DAYS_PER_WEEK step logs are left out, so a partial week doesn't fake a trend.
- Each prediction has an 80% range from the user's own week-to-week variation (at least
  MIN_NOISE), widening with the horizon. Workouts never go above max(plan, best week so far).

The HealthScore forecast uses the backend's own calculation (backend/app/healthscore.py and
healthscore_repo.py, the code behind the HealthScore screen). Each past week is scored as a
7-day window, each category's weekly score is forecast
separately, and the forecasts are combined with the active health_score_config weights, the
same way the screen's overall score is.

    python progress_forecast.py --user <user_id>  # print one user's forecast
    python progress_forecast.py weekly [--dry-run]  # forecast every user, save to progress_forecasts

Run `weekly` once a week (for example from cron on Monday). A user who already has forecasts
from this week and MODEL_VERSION is skipped, so running it twice adds nothing.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import numpy as np

from exercise_ranker import fetch_all

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "backend"))
from app import healthscore as hs  # noqa: E402  (pure functions; healthscore_repo loads lazily)

MODEL_VERSION = "linreg-weekly-v1"
ML_MODEL_VERSION = "linreg+xgb-weekly-v1"
HORIZONS = (1, 4, 12)  # weeks ahead of the last completed week
# A week this many weeks old counts half as much as the most recent one.
WEEK_HALF_LIFE = 4.0
# How firmly the profile prior holds the slope, in the units of the data's own evidence
# (sum of weight * (week - mean week)^2). Four equally weighted weeks give 5.
PRIOR_STRENGTH = 5.0

# Expected weight change per week while doing every planned workout:
# - Loss: CDC recommends 1-2 lb (0.45-0.9 kg) a week; the forecast uses the low end.
# - Gain: Aragon's lean-gain rates, as a share of body weight per month, low end by level.
WEIGHT_LOSS_PER_WEEK = 0.5
MUSCLE_GAIN_PER_MONTH = {"beginner": 0.01, "intermediate": 0.005, "advanced": 0.0025}
WEEKS_PER_MONTH = 52 / 12
MAX_WEEKLY_WEIGHT_CHANGE = 1.0  # kg; the top of the CDC's safe range
# Weeks of HealthScore history to rebuild (scored in memory from one load of the user's logs).
MAX_HEALTH_WEEKS = 12
# Holt's damped trend: week h ahead adds slope * (1 + DAMPING + ... + DAMPING^(h-1)): next week
# follows the full trend, later weeks less, so the total change is at most slope / (1 - DAMPING),
# 5 weeks' worth of the current trend.
DAMPING = 0.8
# 80% prediction range: the 10th to 90th percentile of a normal distribution.
INTERVAL_Z = 1.28
# Typical week-to-week noise per metric. The user's own noise is blended with it as if it were
# NOISE_PRIOR_WEEKS weeks of data, so a couple of weeks can't make the range absurdly wide or narrow.
MIN_NOISE = {"weight_kg": 0.4, "workouts_per_week": 0.7, "daily_steps": 900.0, "health_score": 6.0}
MIN_CATEGORY_NOISE = 8.0
NOISE_PRIOR_WEEKS = 4
# A week of steps needs at least this many logged days to count.
MIN_DAYS_PER_WEEK = 3

METRICS = {
    # prediction_type: (label, unit, lowest, highest)
    "weight_kg": ("Weight", "kg", 30.0, 300.0),
    "workouts_per_week": ("Workouts", "per week", 0.0, 7.0),
    "daily_steps": ("Steps", "per day", 0.0, None),
    "health_score": ("HealthScore", "", 0.0, 100.0),
}


def to_date(value):
    """A date from a Supabase date or timestamp string."""
    return date.fromisoformat(str(value)[:10])


def week_start(day):
    return day - timedelta(days=day.weekday())


def last_complete_week(today):
    """Monday of the most recent week that has fully ended. The current week is still partial."""
    return week_start(today) - timedelta(days=7)


def week_index(day, origin):
    """0 for the origin week, -1 for the week before, and so on."""
    return (week_start(day) - origin).days // 7


def weekly_means(rows, date_key, value_key, origin, min_count=1, first_week=None):
    """[(week index, mean value)] over completed weeks, skipping rows without a value, weeks
    with fewer than min_count values, and weeks before first_week."""
    weeks = {}
    for row in rows:
        if row.get(value_key) is None or not row.get(date_key):
            continue
        t = week_index(to_date(row[date_key]), origin)
        if t <= 0 and (first_week is None or t >= first_week):
            weeks.setdefault(t, []).append(float(row[value_key]))
    return [(t, sum(values) / len(values)) for t, values in sorted(weeks.items()) if len(values) >= min_count]


def first_full_week(first_day, origin):
    """Index of the first week the user was around for all of: the week of first_day if that
    was a Monday, otherwise the next one."""
    return week_index(first_day, origin) + (0 if first_day.weekday() == 0 else 1)


def weekly_workouts(logs, first_day, origin):
    """[(week index, completed workouts)] for every full, completed week since first_day, zeros included."""
    first = first_full_week(first_day, origin)
    counts = {t: 0 for t in range(first, 1)}
    for log in logs:
        if log["completion_status"] == "completed" and log.get("workout_date"):
            t = week_index(to_date(log["workout_date"]), origin)
            if t in counts:
                counts[t] += 1
    return sorted(counts.items())


def fit_trend(points, prior_slope):
    """(level at week 0, slope per week) from a recency-weighted least-squares line.

    The prior is one extra equation, slope = prior_slope, weighted by PRIOR_STRENGTH. That keeps
    the fit defined with a single week of data and lets the user's own trend take over as
    weeks accumulate.
    """
    t = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    root_w = np.sqrt(0.5 ** (-t / WEEK_HALF_LIFE))
    A = np.vstack([np.column_stack([root_w, root_w * t]), [0.0, np.sqrt(PRIOR_STRENGTH)]])
    b = np.append(root_w * y, np.sqrt(PRIOR_STRENGTH) * prior_slope)
    (level, slope), *_ = np.linalg.lstsq(A, b, rcond=None)
    return float(level), float(slope)


def noise(points, level, slope, typical):
    """Week-to-week spread around the fitted line, blended with the metric's typical spread.

    The user's recency-weighted residual variance counts as (weeks - 2) weeks of evidence and the
    typical spread as NOISE_PRIOR_WEEKS; never below the typical spread."""
    if len(points) < 3:
        return typical
    t = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    w = 0.5 ** (-t / WEEK_HALF_LIFE)
    variance = np.sum(w * (y - (level + slope * t)) ** 2) / np.sum(w)
    n = len(points) - 2
    blended = (NOISE_PRIOR_WEEKS * typical ** 2 + n * variance) / (NOISE_PRIOR_WEEKS + n)
    return float(max(typical, np.sqrt(blended)))


def damped(h):
    """How many weeks of the current trend are added h weeks ahead."""
    return sum(DAMPING ** i for i in range(h))


def range_half_width(spread, h):
    """Half of the 80% range h weeks ahead: one week's spread next week, growing with the damped
    trend's uncertainty (at most sqrt(5) times as wide), not without limit."""
    return INTERVAL_Z * spread * np.sqrt(damped(h))


# prediction_type for each HealthScore category's forecast, e.g. health_score_sleep.
CATEGORY_TYPES = {category: f"health_score_{category}" for category in hs.CATEGORIES}


def clip(metric, value, highest=None):
    _, _, lowest, top = METRICS.get(metric, ("", "", 0.0, 100.0))  # categories are 0-100
    highest = highest if highest is not None else top
    value = max(value, lowest)
    return min(value, highest) if highest is not None else value


def forecast(metric, level, slope, points, origin, highest=None):
    """The fitted trend, the weekly history it came from, and its predictions with 80% ranges.

    history is [(Monday of the week, value)]; each prediction's target_date is the Sunday
    ending that week. The trend is damped (see DAMPING); ranges is [(target, low, high)].
    """
    spread = noise(points, level, slope, MIN_NOISE.get(metric, MIN_CATEGORY_NOISE))
    predictions, ranges = [], []
    for h in HORIZONS:
        target = origin + timedelta(days=7 * h + 6)
        value = clip(metric, level + slope * damped(h), highest)
        half = range_half_width(spread, h)
        predictions.append((target, value))
        ranges.append((target, clip(metric, value - half, highest), clip(metric, value + half, highest)))
    return {
        "metric": metric, "level": clip(metric, level, highest), "slope": slope, "weeks_of_data": len(points),
        "history": [(origin + timedelta(days=7 * t), value) for t, value in points],
        "predictions": predictions, "ranges": ranges, "noise": spread,
    }


def goal_weight_slope(profile, weight):
    """kg per week the user's fitness_goal expects when they do every planned workout."""
    if profile["fitness_goal"] == "lose_weight":
        return -WEIGHT_LOSS_PER_WEEK
    if profile["fitness_goal"] == "build_muscle":
        return weight * MUSCLE_GAIN_PER_MONTH[profile["fitness_level"]] / WEEKS_PER_MONTH
    return 0.0


def forecast_health(weeks, weights, origin):
    """The HealthScore forecast from weekly backend results, or None with no scored week.

    weeks is [(Monday, healthscore.build_result output)]. Each category is fit on its own, and
    every prediction is combined with hs.overall_score, which re-weights over the categories
    that have data, as the screen's provisional score does.
    """
    categories = {}
    for category in hs.CATEGORIES:
        points = [(week_index(monday, origin), r[category]) for monday, r in weeks if r[category] is not None]
        if points:
            categories[category] = forecast(CATEGORY_TYPES[category], *fit_trend(points, 0.0), points, origin)
    if not categories:
        return None
    level = hs.overall_score({c: f["level"] for c, f in categories.items()}, weights)
    predictions = [
        (target, hs.overall_score({c: f["predictions"][i][1] for c, f in categories.items()}, weights))
        for i, (target, _) in enumerate(next(iter(categories.values()))["predictions"])
    ]
    history = [(monday, r["overall_score"]) for monday, r in weeks if r["overall_score"] is not None]
    points = [(week_index(monday, origin), value) for monday, value in history]
    spread = noise(points, *fit_trend(points, 0.0), MIN_NOISE["health_score"]) if points else MIN_NOISE["health_score"]
    ranges = [(target, clip("health_score", value - range_half_width(spread, h)),
               clip("health_score", value + range_half_width(spread, h)))
              for h, (target, value) in zip(HORIZONS, predictions)]
    return {
        "metric": "health_score", "level": level, "slope": (predictions[-1][1] - level) / HORIZONS[-1],
        "weeks_of_data": len(history), "history": history, "predictions": predictions, "ranges": ranges,
        "categories": categories, "weights": weights,
        "missing": [c for c in hs.CATEGORIES if c not in categories],
    }


def forecast_user(profile, history, today, workout_days=None, health=None, weight_model=None, use_ml=True):
    """Forecasts for one user, keyed by prediction_type. Metrics with no data are left out.

    profile is a raw Supabase profiles row; history maps body_measurements, workout_logs and
    activity_logs to that user's rows. workout_days is the planned workouts per week (the
    HealthScore's source: plan, then preferences, then onboarding); it defaults to the
    profile's workout_frequency. health is {"weeks": [(Monday, result)], "weights": {...}}
    from health_context, or None to skip the HealthScore.
    """
    origin = last_complete_week(today)
    workout_days = workout_days or profile["workout_frequency"]
    result = {}

    # Workouts: completed per week since the user joined, flat prior. Before a full week has
    # passed, the plan is the forecast.
    logs = history["workout_logs"]
    first_day = min([to_date(profile["created_at"])]
                    + [to_date(log["workout_date"]) for log in logs if log.get("workout_date")])
    points = weekly_workouts(logs, first_day, origin)
    if points:
        level, slope = fit_trend(points, 0.0)
    else:
        level, slope = float(workout_days), 0.0
    # Nobody is forecast to do more than their plan or their best week so far.
    most = min(7.0, max([float(workout_days)] + [value for _, value in points]))
    result["workouts_per_week"] = forecast("workouts_per_week", level, slope, points, origin, highest=most)

    # Weight: body_measurements, or the onboarding weight until the user logs one. The goal's
    # expected rate is scaled by forecast adherence to the planned workouts.
    points = weekly_means(history["body_measurements"], "recorded_at", "weight_kg", origin)
    if not points and profile.get("weight_kg") is not None:
        points = [(min(week_index(to_date(profile["created_at"]), origin), 0), float(profile["weight_kg"]))]
    if points:
        next_week = result["workouts_per_week"]["predictions"][0][1]
        adherence = min(next_week / workout_days, 1.0)
        prior = goal_weight_slope(profile, points[-1][1]) * adherence
        level, slope = fit_trend(points, prior)
        slope = max(-MAX_WEEKLY_WEIGHT_CHANGE, min(slope, MAX_WEEKLY_WEIGHT_CHANGE))
        result["weight_kg"] = forecast("weight_kg", level, slope, points, origin)
        result["weight_kg"]["adherence"] = adherence

    first_activity = min([to_date(profile["created_at"])]
                         + [to_date(r["log_date"]) for r in history["activity_logs"] if r.get("log_date")])
    points = weekly_means(history["activity_logs"], "log_date", "steps", origin,
                          min_count=MIN_DAYS_PER_WEEK, first_week=first_full_week(first_activity, origin))
    if points:
        result["daily_steps"] = forecast("daily_steps", *fit_trend(points, 0.0), points, origin)

    if use_ml and "weight_kg" in result:
        weight_model = weight_model or default_weight_model()
        if weight_model is not None:
            import weight_forecast_model

            weight_forecast_model.apply(weight_model, profile, result, origin)

    if health:
        health_score = forecast_health(health["weeks"], health["weights"], origin)
        if health_score:
            result["health_score"] = health_score
    return result


def default_weight_model():
    import weight_forecast_model

    return weight_forecast_model.load_model()


def forecast_rows(user_id, forecasts, with_ranges=False):
    """progress_forecasts rows for one user: one per metric and horizon. with_ranges adds the
    80% range (low/high) for the API; the table only stores the prediction."""
    results = list(forecasts.values()) + list(forecasts.get("health_score", {}).get("categories", {}).values())
    rows = []
    for result in results:
        for i, (target, value) in enumerate(result["predictions"]):
            row = {"user_id": user_id, "prediction_type": result["metric"], "predicted_value": round(value, 2),
                   "target_date": target.isoformat(), "model_version": result.get("model_version", MODEL_VERSION)}
            if with_ranges and result.get("ranges"):
                _, low, high = result["ranges"][i]
                row.update(low=round(low, 2), high=round(high, 2))
            rows.append(row)
    return rows


def forecast_history(forecasts):
    """{prediction_type: [{"week_start", "value"}]} - the weekly history each forecast was fitted on."""
    results = list(forecasts.values()) + list(forecasts.get("health_score", {}).get("categories", {}).values())
    return {result["metric"]: [{"week_start": monday.isoformat(), "value": round(float(value), 2)}
                               for monday, value in result["history"]]
            for result in results}


HISTORY_TABLES = {
    # table: (columns, primary key)
    "body_measurements": ("user_id, recorded_at, weight_kg", "measurement_id"),
    "workout_logs": ("user_id, workout_date, completion_status", "workout_log_id"),
    "activity_logs": ("user_id, log_date, steps", "activity_id"),
}


def load_history(client, user_id=None):
    """{user_id: {table: rows}} for one user, or for everyone when user_id is None."""
    history = {}
    for table, (columns, key) in HISTORY_TABLES.items():
        for row in fetch_all(client, table, columns, key, user_id):
            history.setdefault(row["user_id"], {t: [] for t in HISTORY_TABLES})[table].append(row)
    return history


def health_context(client, profile, history, today):
    """Planned workout days and weekly HealthScore results, from the backend's HealthScore code.

    Weeks are scored from the earlier of sign-up and the first logged workout or activity, up
    to MAX_HEALTH_WEEKS complete weeks back.
    """
    from app import healthscore_repo as repo

    origin = last_complete_week(today)
    logged = [to_date(r["workout_date"]) for r in history["workout_logs"] if r.get("workout_date")]
    logged += [to_date(r["log_date"]) for r in history["activity_logs"] if r.get("log_date")]
    first_day = min([to_date(profile["created_at"])] + logged)
    first = max(origin + timedelta(weeks=first_full_week(first_day, origin)),
                origin - timedelta(weeks=MAX_HEALTH_WEEKS - 1))
    # One load of the user's settings and logs, then each week is scored in memory.
    ctx = repo.load_contexts(client, profile["user_id"])[profile["user_id"]]
    logs = repo.load_logs(client, first, origin + timedelta(days=6), profile["user_id"])[profile["user_id"]]
    weights, _ = repo.active_weights(client)
    weeks = []
    monday = first
    while monday <= origin:
        weeks.append((monday, repo.score(ctx, logs, weights, monday, monday + timedelta(days=6))))
        monday += timedelta(weeks=1)
    return {"workout_days": ctx.days_per_week, "health": {"weeks": weeks, "weights": weights}}


def forecast_from_supabase(client, user_id, today=None, context=health_context):
    today = today or datetime.now(timezone.utc).date()
    profiles = fetch_all(client, "profiles", "*", "user_id", user_id)
    if not profiles:
        raise LookupError(f"No profile found for user {user_id}.")
    history = load_history(client, user_id).get(user_id, {t: [] for t in HISTORY_TABLES})
    return forecast_user(profiles[0], history, today, **context(client, profiles[0], history, today))


def run_weekly(client, today=None, dry_run=False, context=health_context):
    """Forecast every user without forecasts from this week, and save them. Returns rows saved."""
    today = today or datetime.now(timezone.utc).date()
    this_week = week_start(today)
    done = {
        row["user_id"]
        for row in fetch_all(client, "progress_forecasts", "user_id, generated_at, model_version", "forecast_id")
        if row["model_version"] in (MODEL_VERSION, ML_MODEL_VERSION) and to_date(row["generated_at"]) >= this_week
    }
    history = load_history(client)
    rows = []
    for profile in fetch_all(client, "profiles", "*", "user_id"):
        if profile["user_id"] not in done:
            user_history = history.get(profile["user_id"], {t: [] for t in HISTORY_TABLES})
            extra = context(client, profile, user_history, today)
            rows += forecast_rows(profile["user_id"], forecast_user(profile, user_history, today, **extra))
    if rows and not dry_run:
        client.table("progress_forecasts").insert(rows).execute()
    return rows


def format_forecast(forecasts):
    corrected = "baseline_predictions" in forecasts.get("weight_kg", {})
    lines = ["\n--- Forecast (linear regression" + (" + XGBoost weight correction" if corrected else "")
             + ", refit weekly) ---"]
    for metric, (label, unit, _, _) in METRICS.items():
        result = forecasts.get(metric)
        if result is None:
            lines.append(f"{label}: no data yet")
            continue
        unit = f" {unit}" if unit else ""
        ahead = ", ".join(f"{value:.1f} in {h} wk" for h, (_, value) in zip(HORIZONS, result["predictions"]))
        weeks = result["weeks_of_data"]
        line = (f"{label}: {result['level']:.1f}{unit} now -> {ahead} "
                f"({result['slope']:+.2f}/wk, {weeks} {'week' if weeks == 1 else 'weeks'} of data)")
        if "adherence" in result:
            line += f"; assumes {result['adherence']:.0%} of planned workouts"
        lines.append(line)
        if "baseline_predictions" in result:
            base = ", ".join(f"{value:.1f}" for _, value in result["baseline_predictions"])
            lines.append(f"  Linear baseline alone: {base} kg; XGBoost moved it by "
                         + ", ".join(f"{fix:+.1f}" for fix in result["ml_corrections"]) + " kg")
        for category, part in result.get("categories", {}).items():
            lines.append(f"  {category.title()}: {part['level']:.0f} now -> "
                         f"{part['predictions'][-1][1]:.0f} in {HORIZONS[-1]} wk "
                         f"(weight {result['weights'][category]:.0%})")
        if result.get("missing"):
            lines.append(f"  Not logged yet: {', '.join(c.title() for c in result['missing'])}")
    return "\n".join(lines)


def main():
    import importlib.util

    spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
    recommender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recommender)

    if sys.argv[1:2] == ["weekly"]:
        dry_run = "--dry-run" in sys.argv
        rows = run_weekly(recommender.supabase_client(), dry_run=dry_run)
        print(f"{'Would save' if dry_run else 'Saved'} {len(rows)} forecasts to progress_forecasts.")
    elif "--user" in sys.argv and sys.argv.index("--user") + 1 < len(sys.argv):
        user_id = sys.argv[sys.argv.index("--user") + 1]
        print(format_forecast(forecast_from_supabase(recommender.supabase_client(), user_id)))
    else:
        print("Usage: python progress_forecast.py --user <user_id> | weekly [--dry-run]")


if __name__ == "__main__":
    main()
