"""Export the sample user's weeks (plans, adaptation, ranker effect, forecasts) as JSON for the frontend.

Uses SAMPLE_USER and WEEKS from Sample_User.py, the same planning code as the app, the trained
models if they exist (models/exercise_ranker.json, models/adaptive_week_two.json), and
progress_forecast.forecast_user for the forecast after each week. Nothing is read from or
written to Supabase.

    python export_sample_user.py                  # writes public/sample_user.json
    python export_sample_user.py other/path.json

`npm run dev` and `npm run build` run this first (package.json "sample-data"), so the HealthScore
screen's Sample Player section always shows the current plans, models and forecast. Vite serves
everything in public/ at the site root, so the page fetches it as /sample_user.json.
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import adaptive_week_two
import exercise_ranker
import progress_forecast as pf
import weekly_plan
from Sample_User import FIRST_MONDAY, SAMPLE_USER, WEEKS, changes_between, parse_log

recommender = weekly_plan.recommender
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "public" / "sample_user.json"  # Vite serves public/ at the site root
START_WEIGHT_KG = 75.0  # onboarding weight for the sample user


def plan_json(profile, plan):
    return {
        "week_start": plan["week_start"].isoformat(), "days": plan["days"],
        "items": [{"day": i["day"], "group": i["group"], "name": i["exercise"]["name"],
                   "level": i["exercise"]["level"], "equipment": i["exercise"]["equipment"] or "none",
                   "dose": weekly_plan.dose_text(profile, i)}
                  for i in sorted(plan["items"], key=lambda i: (i["day"], i["group"]))],
    }


def ranker_effect(with_model, without_model):
    a = {(i["day"], i["group"]): i["exercise"]["name"] for i in without_model["items"]}
    b = {(i["day"], i["group"]): i["exercise"]["name"] for i in with_model["items"]}
    return [{"day": d, "group": g, "rules_pick": a.get((d, g)), "ranker_pick": b.get((d, g))}
            for d, g in sorted(set(a) | set(b)) if a.get((d, g)) != b.get((d, g))]


def metric_json(forecast):
    if not forecast:
        return None
    return {
        "level": round(forecast["level"], 2), "slope": round(forecast["slope"], 3),
        "weeks_of_data": forecast["weeks_of_data"],
        "history": [{"week": monday.isoformat(), "value": round(v, 2)} for monday, v in forecast["history"]],
        "predictions": [{"date": d.isoformat(), "weeks_ahead": h, "value": round(v, 2)}
                        for h, (d, v) in zip(pf.HORIZONS, forecast["predictions"])],
        "uses_xgboost": "baseline_predictions" in forecast,
    }


def build():
    exercises = recommender.load_exercises()
    model = exercise_ranker.load_model()
    adapt_model = adaptive_week_two.load_model()
    profile = dict(SAMPLE_USER)
    forecast_profile = {**profile, "created_at": FIRST_MONDAY.isoformat() + "T08:00:00+00:00",
                        "weight_kg": START_WEIGHT_KG}
    history = {"body_measurements": [], "workout_logs": [], "activity_logs": []}

    plan = weekly_plan.first_week(profile, exercises, FIRST_MONDAY, model)
    weeks = [{"week": 1, "story": "Week 1: built from the profile", "profile": dict(profile),
              "plan": plan_json(profile, plan), "changes": [],
              "ranker_effect": ranker_effect(plan, weekly_plan.first_week(profile, exercises, FIRST_MONDAY))
              if model else []}]

    for number, week in enumerate(WEEKS, start=1):
        logs = [parse_log(day, text) for day, text in enumerate(week["logs"][:plan["days"]], start=1)]
        # The same week as dated workout_logs rows, so the forecast sees it too.
        for log in logs:
            history["workout_logs"].append({
                "workout_date": (plan["week_start"] + timedelta(days=log["day_number"] - 1)).isoformat(),
                "completion_status": log["completion_status"]})
        new_profile = {**profile, **week["change"]}
        next_plan = weekly_plan.next_week(new_profile, exercises, plan, logs, model, adapt_model)
        adaptation = next_plan["adaptation"]
        decision, days = adaptation["decision"], adaptation["days"]

        # Forecast as of the day after this week ends, when this week is the latest complete one.
        today = plan["week_start"] + timedelta(days=8)
        forecast_profile.update(week["change"])
        forecast = pf.forecast_user(forecast_profile, history, today, workout_days=next_plan["days"])

        this = weeks[-1]
        this.update({
            "logged": logs, "completion": adaptation["completion"],
            "decision": decision, "days_next": days, "profile_change": week["change"],
            "adaptation": adaptation,
            "result_story": week["story"],
            "forecast": {"as_of": today.isoformat(),
                         "workouts_per_week": metric_json(forecast.get("workouts_per_week")),
                         "weight_kg": metric_json(forecast.get("weight_kg"))},
        })
        weeks.append({
            "week": number + 1, "story": f"Week {number + 1}: adapted from week {number}",
            "profile": dict(new_profile), "plan": plan_json(new_profile, next_plan),
            "changes": changes_between(profile, plan, new_profile, next_plan),
            "ranker_effect": ranker_effect(next_plan, weekly_plan.next_week(new_profile, exercises, plan, logs,
                                                                            None, adapt_model))
            if model else [],
        })
        profile, plan = new_profile, next_plan

    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ranker_used": model is not None, "adaptation_model_used": adapt_model is not None,
            "user": SAMPLE_USER, "weeks": weeks}


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    output.write_text(json.dumps(data, indent=1))
    print(f"Wrote {len(data['weeks'])} weeks to {output} (ranker {'on' if data['ranker_used'] else 'off'}).")


if __name__ == "__main__":
    main()
