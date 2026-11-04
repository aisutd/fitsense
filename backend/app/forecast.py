"""HealthScore forecast: where a player's HealthScore is heading, and how workouts change it.

Each complete Monday-Sunday week is scored with the same functions as the HealthScore screen
(healthscore.py + the goals, plan and weights from healthscore_repo.py). Each category is then
fit with a recency-weighted straight line (a week 4 weeks old counts half as much as the latest,
the same model as progress_forecast.py), predicted 1, 4 and 12 weeks ahead, and combined with
the active weights exactly as the screen combines them.

What-if scenarios hold the Workouts category at the score that k completed workouts a week would
earn (completed / scheduled x 100, capped at 100) while the other categories follow their trends,
so the player can see how many workouts it takes to reach a HealthScore.

Pure Python (no numpy) so it runs inside the backend container. Before a complete week exists,
the last 7 days are used as a single starting point. HealthScore is a motivational wellness
metric, not a medical assessment.
"""

from collections import defaultdict
from datetime import date, timedelta

from supabase import Client

from app import healthscore as hs
from app import healthscore_repo as repo

HORIZONS = (1, 4, 12)    # weeks ahead of the last complete week
WEEK_HALF_LIFE = 4.0     # a week this many weeks old counts half as much as the latest
PRIOR_STRENGTH = 5.0     # how firmly the slope is held at 0 with little data
MAX_WEEKS = 12           # weeks of history to score
MAX_WORKOUTS_PER_WEEK = 7


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def fit_trend(points: list[tuple[int, float]], prior_slope: float = 0.0) -> tuple[float, float]:
    """(level at week 0, slope per week): weighted least squares plus one prior equation on the slope.

    points are (week index, value) with week 0 the latest complete week and earlier weeks negative.
    Same model as progress_forecast.fit_trend, solved from its 2x2 normal equations.
    """
    sw = swt = swtt = swy = swty = 0.0
    for t, y in points:
        w = 0.5 ** (-t / WEEK_HALF_LIFE)
        sw += w
        swt += w * t
        swtt += w * t * t
        swy += w * y
        swty += w * t * y
    a11, a12, a22 = sw, swt, swtt + PRIOR_STRENGTH
    b1, b2 = swy, swty + PRIOR_STRENGTH * prior_slope
    det = a11 * a22 - a12 * a12
    return (b1 * a22 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _bucket(rows: list[dict], date_col: str, mondays: list[date]) -> dict[date, list[dict]]:
    weeks = defaultdict(list)
    first, last = mondays[0], mondays[-1] + timedelta(days=6)
    for row in rows:
        if not row.get(date_col):
            continue
        day = date.fromisoformat(str(row[date_col])[:10])
        if first <= day <= last:
            weeks[week_start(day)].append(row)
    return weeks


def weekly_results(supabase: Client, user_id: str, profile: dict, end_date: date) -> dict:
    """Score every complete week (up to MAX_WEEKS) since the player started, in four queries.

    Returns {"mondays", "results": {Monday: build_result}, "workouts": {Monday: credited count},
    "days_per_week", "weights", "last_7_days": build_result for the 7 days ending end_date}.
    """
    origin = week_start(end_date) - timedelta(weeks=1)          # latest complete week
    window_start = origin - timedelta(weeks=MAX_WEEKS - 1)
    goals = repo.current_goals(supabase, user_id, profile)
    days_per_week = repo.workout_days_per_week(supabase, user_id, profile)
    weights, _ = repo.active_weights(supabase)

    workouts = repo._in_window(supabase, "workout_logs", "workout_date, completion_status", user_id,
                               "workout_date", window_start, end_date)
    meals = repo._in_window(supabase, "meal_entries", "log_date, calories, protein_g, carbs_g, fat_g",
                            user_id, "log_date", window_start, end_date, status="confirmed")
    sleep = repo._in_window(supabase, "sleep_logs", "sleep_date, hours_slept", user_id, "sleep_date",
                            window_start, end_date)
    activity = repo._in_window(supabase, "activity_logs", "log_date, steps, active_minutes", user_id,
                               "log_date", window_start, end_date)

    # Start at the earlier of sign-up and the first log, so weeks before the player existed aren't zeros.
    starts = [date.fromisoformat(str(r[c])[:10]) for rows, c in
              ((workouts, "workout_date"), (meals, "log_date"), (sleep, "sleep_date"), (activity, "log_date"))
              for r in rows if r.get(c)]
    if profile.get("created_at"):
        starts.append(date.fromisoformat(str(profile["created_at"])[:10]))
    first = max(week_start(min(starts)), window_start) if starts else origin + timedelta(weeks=1)
    mondays = [first + timedelta(weeks=i) for i in range((origin - first).days // 7 + 1)] if first <= origin else []

    def score(w, m, s, a, days):
        return hs.build_result({
            "workouts": hs.score_workouts([r["completion_status"] for r in w], days_per_week, days),
            "nutrition": hs.score_nutrition(repo.daily_meal_totals(m), goals["nutrition"], days,
                                            targets_estimated=goals["nutrition_estimated"]),
            "sleep": hs.score_sleep([repo._num(r["hours_slept"]) for r in s if r.get("hours_slept") is not None],
                                    goals["sleep_target_hours"]),
            "activity": hs.score_activity(a, goals["daily_steps"], goals["daily_active_minutes"]),
        }, weights)

    results, credited = {}, {}
    if mondays:
        by_week = [_bucket(rows, col, mondays) for rows, col in
                   ((workouts, "workout_date"), (meals, "log_date"), (sleep, "sleep_date"), (activity, "log_date"))]
        for monday in mondays:
            w, m, s, a = (b.get(monday, []) for b in by_week)
            results[monday] = score(w, m, s, a, 7)
            credited[monday] = (sum(1 for r in w if r["completion_status"] == "completed")
                                + hs.PARTIAL_WORKOUT_CREDIT * sum(1 for r in w if r["completion_status"] == "partial"))

    recent_start = end_date - timedelta(days=6)
    in_recent = lambda rows, col: [r for r in rows if r.get(col) and str(r[col])[:10] >= recent_start.isoformat()]
    last_7 = score(in_recent(workouts, "workout_date"), in_recent(meals, "log_date"),
                   in_recent(sleep, "sleep_date"), in_recent(activity, "log_date"), 7)
    return {"origin": origin, "mondays": mondays, "results": results, "workouts": credited,
            "days_per_week": days_per_week, "weights": weights, "last_7_days": last_7}


def _overall(parts: dict[str, float], weights: dict[str, float]) -> float | None:
    value = hs.overall_score(parts, weights)
    return round(value, 1) if value is not None else None


def build_forecast(data: dict) -> dict:
    """The forecast and what-if scenarios from weekly_results() output. Pure: no database access."""
    origin, mondays, results, weights = data["origin"], data["mondays"], data["results"], data["weights"]
    index = lambda monday: (monday - origin).days // 7
    targets = [(h, (origin + timedelta(weeks=h, days=6)).isoformat()) for h in HORIZONS]

    scored = [m for m in mondays if results[m]["overall_score"] is not None]
    if scored:
        based_on = "complete_weeks"
        series = {c: [(index(m), results[m][c]) for m in mondays if results[m][c] is not None] for c in hs.CATEGORIES}
    elif data["last_7_days"]["overall_score"] is not None:
        based_on = "last_7_days"
        series = {c: ([(0, data["last_7_days"][c])] if data["last_7_days"][c] is not None else []) for c in hs.CATEGORIES}
    else:
        return {"based_on": "none", "weeks_of_data": 0, "history": [], "trend": None, "scenarios": [],
                "pace": None, "planned_workouts_per_week": data["days_per_week"], "weights": weights,
                "missing": list(hs.CATEGORIES)}

    categories = {}
    for category, points in series.items():
        if points:
            level, slope = fit_trend(points)
            categories[category] = {
                "level": round(_clip(level), 1), "slope": round(slope, 2), "weeks_of_data": len(points),
                "predictions": [{"weeks_ahead": h, "date": d, "value": round(_clip(level + slope * h), 1)}
                                for h, d in targets],
            }
    predicted = lambda c, i: categories[c]["predictions"][i]["value"]
    trend = {
        "now": _overall({c: f["level"] for c, f in categories.items()}, weights),
        "predictions": [{"weeks_ahead": h, "date": d, "value": _overall({c: predicted(c, i) for c in categories}, weights)}
                        for i, (h, d) in enumerate(targets)],
        "categories": categories,
    }

    # Current pace: credited workouts per complete week (zeros included), the same line model.
    pace = None
    if data["workouts"]:
        level, slope = fit_trend([(index(m), n) for m, n in data["workouts"].items()])
        pace = round(_clip(level + slope, 0, MAX_WORKOUTS_PER_WEEK), 1)

    planned = data["days_per_week"]
    scenarios = []
    if planned:
        scheduled = hs.scheduled_workouts(planned, 7)
        others = [c for c in categories if c != "workouts"]

        def scenario(per_week: float) -> dict:
            workout_score = round(hs.workout_score(per_week, scheduled), 1)
            return {"workouts_per_week": per_week, "workout_score": workout_score,
                    "predictions": [{"weeks_ahead": h, "date": d,
                                     "value": _overall({**{c: predicted(c, i) for c in others},
                                                        "workouts": workout_score}, weights)}
                                    for i, (h, d) in enumerate(targets)]}

        scenarios = [scenario(k) for k in range(0, min(planned + 1, MAX_WORKOUTS_PER_WEEK) + 1)]
        pace_scenario = scenario(pace) if pace is not None else None
    else:
        pace_scenario = None

    history = [{"week_start": m.isoformat(), "overall": results[m]["overall_score"],
                **{c: results[m][c] for c in hs.CATEGORIES}} for m in mondays]
    return {
        "based_on": based_on, "weeks_of_data": len(scored), "history": history, "trend": trend,
        "pace": ({"workouts_per_week": pace, **pace_scenario} if pace_scenario else None),
        "scenarios": scenarios, "planned_workouts_per_week": planned,
        "scheduled_per_week": hs.scheduled_workouts(planned, 7) if planned else None,
        "weights": weights, "missing": [c for c in hs.CATEGORIES if c not in categories],
    }


def healthscore_forecast(supabase: Client, user_id: str, end_date: date) -> dict:
    profile = repo.get_profile(supabase, user_id)
    forecast = build_forecast(weekly_results(supabase, user_id, profile, end_date))
    return {"user_id": user_id, "end_date": end_date.isoformat(), "horizons": list(HORIZONS), **forecast}
