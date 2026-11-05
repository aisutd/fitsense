"""What-if scenarios for the HealthScore forecast: how many workouts a week move it.

progress_forecast.forecast_health already projects each HealthScore category 1, 4 and 12 weeks
ahead. A scenario keeps those projections for nutrition, sleep and activity, holds the Workouts
category at the score k completed workouts a week would earn (completed / scheduled x 100, capped
at 100, the HealthScore's own rule), and recombines them with the active weights exactly as the
screen does. Pure functions: no database access.
"""

from app import healthscore as hs

MAX_WORKOUTS_PER_WEEK = 7


def workout_scenarios(forecast: dict, days_per_week: int | None) -> dict | None:
    """Scenarios from a progress_forecast.forecast_user result, or None without a HealthScore
    forecast or a workout plan."""
    health = forecast.get("health_score")
    if not health or not days_per_week:
        return None
    categories, weights = health["categories"], health["weights"]
    targets = [target for target, _ in health["predictions"]]
    others = [c for c in categories if c != "workouts"]
    scheduled = hs.scheduled_workouts(days_per_week, 7)

    def scenario(per_week: float) -> dict:
        workout_score = hs.workout_score(per_week, scheduled)
        predictions = []
        for i, target in enumerate(targets):
            parts = {c: categories[c]["predictions"][i][1] for c in others}
            parts["workouts"] = workout_score
            predictions.append({"target_date": target.isoformat(),
                                "value": round(hs.overall_score(parts, weights), 1)})
        return {"workouts_per_week": per_week, "workout_score": round(workout_score, 1), "predictions": predictions}

    pace = forecast.get("workouts_per_week")
    pace_per_week = round(min(max(pace["predictions"][0][1], 0.0), MAX_WORKOUTS_PER_WEEK), 1) if pace else None
    return {
        "planned_per_week": days_per_week,
        "scheduled_per_week": scheduled,
        "trend": [{"target_date": target.isoformat(), "value": round(value, 1)} for target, value in health["predictions"]],
        "pace": scenario(pace_per_week) if pace_per_week is not None else None,
        # 0 up to one more than the plan, so the cap at the plan is visible
        "options": [scenario(k) for k in range(0, min(days_per_week + 1, MAX_WORKOUTS_PER_WEEK) + 1)],
    }
