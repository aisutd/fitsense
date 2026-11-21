"""This week's workout plan for one player, from the weekly plan model (weekly_plan.py at the repo root).

The model builds week 1 from the profile (goal, level, location, equipment) and adapts every later
week to how many of last week's plan days the player completed (with adaptation_model.py's
XGBoost model when its file exists, else fixed thresholds). Every week keeps at least one
recovery day; the schedule spreads the plan days over the week with recovery days between them. Plans are saved in workout_plans /
plan_exercises; workout_logs with plan_id + day_number say how each plan day went.

When a player can't do a day as planned (the equipment is broken, they can't get to the gym),
swap_day() swaps the exercises that no longer fit for the closest ones that do (day_swaps.py), for
that day or the rest of the week. A day skipped for one of those reasons is excused: it isn't
counted as missed by next week's plan, the HealthScore or the forecast.
"""

import importlib
import os
import sys
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

STATUS_RANK = {"skipped": 0, "partial": 1, "completed": 2}
ADAPTATION_TEXT = {
    "progress": "You finished last week's plan, so this week steps up.",
    "same dose": "You did most of last week's plan, so this week keeps the same doses.",
    "reduce": "Last week was hard to fit in, so this week is a little lighter.",
}
# When the adaptation model picked the change, from its predicted completion rather than a threshold.
MODEL_ADAPTATION_TEXT = {
    "progress": "From how your weeks have gone, you're likely to finish a step up, so this week steps up.",
    "same dose": "This week keeps the same doses, the most you're likely to finish right now.",
    "reduce": "This week is a little lighter, so you're more likely to finish it.",
}
# skip_reason -> how the excuse reads ("the gym was out of reach")
EXCUSES = {"no_equipment": "the equipment wasn't available", "location": "you couldn't get to the gym"}
LOG_COLUMNS = "workout_log_id, plan_id, day_number, completion_status, workout_date"


@lru_cache
def model_module(name: str):
    """A module from the repository root (weekly_plan, exercise_ranker), also in the backend image."""
    root = str(Path(os.getenv("FITSENSE_FORECAST_ROOT", Path(__file__).resolve().parents[2])))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(name)


@lru_cache
def exercises() -> dict:
    return model_module("weekly_plan").recommender.load_exercises()


@lru_cache
def ranker():
    return model_module("exercise_ranker").load_model()   # None until a model is trained


@lru_cache
def adapter():
    return model_module("adaptation_model").load_model()   # None without a model: the rules decide


def _profile(client, user_id: str) -> dict:
    rows = (client.table("profiles").select("*, user_preferences(available_equipment), user_gamification(total_xp)")
            .eq("user_id", user_id).limit(1).execute().data)
    if not rows:
        raise HTTPException(status_code=404, detail="Profile not found")
    return model_module("weekly_plan").recommender.profile_from_supabase_row(rows[0])


def saved_plans(client, user_id: str) -> list[tuple[str, dict]]:
    """[(plan_id, plan)] oldest first - weekly_plan.load_plans for one user, reading only their rows."""
    wp = model_module("weekly_plan")
    by_name = {e["name"].strip().lower(): e for e in exercises()["home"] + exercises()["gym"]}
    plans = {}
    for row in (client.table("workout_plans").select("plan_id, days_per_week, week_start")
                .eq("user_id", user_id).execute().data):
        if row["week_start"]:
            plans[row["plan_id"]] = {"week_start": wp.to_date(row["week_start"]), "days": row["days_per_week"], "items": []}
    if plans:
        rows = (client.table("plan_exercises").select("plan_id, day_number, sets, reps, duration_minutes, exercises(name)")
                .in_("plan_id", list(plans)).limit(5000).execute().data)
        for row in rows:
            exercise = by_name.get(((row.get("exercises") or {}).get("name") or "").strip().lower())
            if exercise:
                plans[row["plan_id"]]["items"].append(
                    {"day": row["day_number"], "group": wp.recommender.muscle_group(exercise), "exercise": exercise,
                     "sets": row["sets"], "reps": row["reps"], "minutes": row["duration_minutes"]})
    for plan in plans.values():
        plan["items"].sort(key=lambda item: item["day"])
    return sorted(plans.items(), key=lambda pair: pair[1]["week_start"])


def _plan_logs(client, user_id: str) -> list[dict]:
    """The player's workout logs, with skip_reason and swapped once backend/sql/009 has added them."""
    def read(columns):
        return client.table("workout_logs").select(columns).eq("user_id", user_id).execute().data
    try:
        return read(LOG_COLUMNS + ", skip_reason, swapped")
    except Exception:   # before 009: every skip counts, as it used to
        return read(LOG_COLUMNS)


def link_logs(saved: list[tuple[str, dict]], logs: list[dict]) -> list[dict]:
    return model_module("weekly_plan").link_logs(saved, logs)


def plan_day_for(client, user_id: str, workout_date: date) -> tuple[str, int] | None:
    """(plan_id, day_number) to link a new workout log to: the next open day of that week's plan."""
    monday = workout_date - timedelta(days=workout_date.weekday())
    plan = (client.table("workout_plans").select("plan_id, days_per_week").eq("user_id", user_id)
            .eq("week_start", monday.isoformat()).limit(1).execute().data)
    if not plan:
        return None
    week_logs = (client.table("workout_logs").select("workout_log_id, plan_id, day_number, workout_date, completion_status")
                 .eq("user_id", user_id).gte("workout_date", monday.isoformat())
                 .lte("workout_date", (monday + timedelta(days=6)).isoformat()).execute().data)
    saved = [(plan[0]["plan_id"], {"week_start": monday, "days": plan[0]["days_per_week"]})]
    taken = {l["day_number"] for l in link_logs(saved, week_logs) if l.get("plan_id") == plan[0]["plan_id"]}
    free = [d for d in range(1, plan[0]["days_per_week"] + 1) if d not in taken]
    return (plan[0]["plan_id"], free[0]) if free else None


def current_plan(client, user_id: str, today: date) -> dict:
    """This week's plan (built and saved on first view), with each day's status and why it changed."""
    wp = model_module("weekly_plan")
    profile = _profile(client, user_id)
    start = wp.week_start(today)
    saved = saved_plans(client, user_id)
    logs = link_logs(saved, _plan_logs(client, user_id))

    current = next(((pid, p) for pid, p in saved if p["week_start"] == start), None)
    if current is None:
        plan = wp.plan_for_week(profile, exercises(), saved, logs, start, ranker(), adapter())
        ids, _ = wp.sync_exercises(client, exercises())
        plan_row, exercise_rows = wp.plan_rows(user_id, profile, plan, ids)
        client.table("workout_plans").insert(plan_row).execute()
        wp.insert(client, "plan_exercises", exercise_rows)
        current = (plan_row["plan_id"], plan)
        logs = link_logs(saved + [current], logs)   # workouts already logged this week count toward it
    plan_id, plan = current

    # How last week went, which is what shaped this one.
    previous = next(((pid, p) for pid, p in reversed(saved) if p["week_start"] < start), None)
    adaptation = None
    if previous:
        prev_logs = [log for log in logs if log["plan_id"] == previous[0]]
        result = wp.adapt(profile, previous[1], prev_logs, adapter(),
                          wp.earlier_rates(saved, logs, previous[1]["week_start"]))
        change, predicted = result["change"], result["predicted"]
        excused = sorted(wp.excused_days(previous[1], prev_logs))
        text = (MODEL_ADAPTATION_TEXT if predicted else ADAPTATION_TEXT)[change]
        if excused:
            text += (f" Day {', '.join(map(str, excused))} {'was' if len(excused) == 1 else 'were'} skipped for reasons "
                     "out of your hands, so it didn't count against you.")
        adaptation = {"change": change, "text": text,
                      "decided_by": "model" if predicted else "rules",
                      "predicted_completion": round(predicted[change], 2) if predicted else None,
                      # leaving out excused days
                      "last_week_completion": round(wp.completion_rate(previous[1], prev_logs), 2),
                      "excused_days": excused}

    statuses: dict[int, dict] = {}
    for log in logs:
        if log["plan_id"] == plan_id and log.get("day_number"):
            best = statuses.get(log["day_number"])
            if best is None or STATUS_RANK[log["completion_status"]] > STATUS_RANK[best["status"]]:
                statuses[log["day_number"]] = {"status": log["completion_status"], "date": str(log["workout_date"])[:10],
                                               "excuse": log.get("skip_reason") if log["completion_status"] == "skipped" else None,
                                               "swapped": bool(log.get("swapped"))}

    def exercise_out(item):
        return {"name": item["exercise"]["name"], "group": item["group"], "category": item["exercise"]["category"],
                "level": item["exercise"]["level"], "equipment": item["exercise"]["equipment"],
                "dose": wp.dose_text(profile, item), "instructions": item["exercise"]["instructions"],
                "primary_muscles": item["exercise"].get("primaryMuscles", []),
                "secondary_muscles": item["exercise"].get("secondaryMuscles", [])}

    # Which day of the week each plan day falls on, with recovery days between them.
    logged = {day: date.fromisoformat(s["date"]) for day, s in statuses.items()}
    schedule = wp.week_schedule(start, plan["days"], logged, today)
    planned_on = {entry["day"]: entry["date"].isoformat() for entry in schedule if entry["day"]}

    days = []
    for day in range(1, plan["days"] + 1):
        items = [item for item in plan["items"] if item["day"] == day]
        days.append({
            "day": day,
            "status": (statuses.get(day) or {}).get("status"),
            "logged_on": (statuses.get(day) or {}).get("date"),
            # why it was skipped, if the reason excuses it ("no_equipment" / "location"), and whether it was done swapped
            "excuse": (statuses.get(day) or {}).get("excuse") if (statuses.get(day) or {}).get("excuse") in EXCUSES else None,
            "swapped": (statuses.get(day) or {}).get("swapped", False),
            "scheduled_on": planned_on.get(day),
            "exercises": [exercise_out(item) for item in items],
        })
    routine = wp.recovery_routine(profile, exercises())
    return {
        "plan_id": plan_id, "week_start": start.isoformat(), "week_end": (start + timedelta(days=6)).isoformat(),
        "days_per_week": plan["days"], "planned_per_profile": profile["workout_frequency"],
        "goal": profile["fitness_goal"], "level": profile["fitness_level"], "location": profile["workout_location"],
        "adaptation": adaptation, "days": days,
        "schedule": [{"date": e["date"].isoformat(), "weekday": e["weekday"], "kind": e["kind"], "day": e["day"]}
                     for e in schedule],
        "recovery": {"walk": routine["walk"], "exercises": [exercise_out(item) for item in routine["stretches"]]},
        "done": sum(1 for d in days if d["status"] == "completed"),
    }


def swap_day(client, user_id: str, today: date, day: int, conditions: dict, force_names=(), rest_of_week=False) -> dict:
    """Swap what a player can't do on a plan day for the closest exercises they can (day_swaps.py),
    saved to this week's plan.

    conditions: {"location", "equipment", "without"}, for this change only (the profile isn't changed).
    rest_of_week: also every other plan day this week that isn't logged yet. Returns the swaps and
    the updated plan.
    """
    wp, swaps_module = model_module("weekly_plan"), model_module("day_swaps")
    before = current_plan(client, user_id, today)        # makes sure this week's plan exists
    if day > before["days_per_week"]:
        raise HTTPException(status_code=422, detail=f"This week's plan has {before['days_per_week']} days")
    profile = _profile(client, user_id)
    start = wp.week_start(today)
    plan_id, plan = next((pid, p) for pid, p in saved_plans(client, user_id) if p["week_start"] == start)
    days = {day}
    if rest_of_week:
        days |= {d["day"] for d in before["days"] if d["status"] is None}
    _, swaps = swaps_module.swap_days(profile, plan, days, conditions, exercises(), force_names, ranker())
    saved = swaps_module.save_swaps(client, plan_id, swaps, exercises())
    return {
        "swaps": [{"day": s["day"], "group": s["group"], "from": s["old"]["name"],
                   "to": s["new"]["name"] if s["new"] else None, "dose": s["new_dose"] or s["old_dose"],
                   "reason": s["reason"]} for s in swaps],
        "days": sorted(days),
        "saved": saved,
        "plan": current_plan(client, user_id, today),
    }
