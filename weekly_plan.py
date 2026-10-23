"""Weekly workout plans saved to Supabase, adapted each week to how the user did last week.

Week 1 comes from the profile: the recommender's exercises spread over workout_frequency days,
each dose at the bottom of its guideline range (see prescribe() in Fitsense-Issue-5.py). From
week 2 on, the plan is rebuilt from last week's plan and the workout_logs linked to it
(plan_id + day_number). Completion = (completed days + half the partial days) / planned days:

- at least PROGRESS_RATE with no skipped day: one step up in dose, and one more day (up to
  workout_frequency) if a reduced week came before
- at least REPEAT_RATE: same dose
- below that: one more day than they did (up to workout_frequency), one step down in dose

On top of that, an exercise that was only on skipped days is swapped for the next-ranked one in
its group, and one on a partial or skipped day steps down. Doses never leave the guideline range.

    python weekly_plan.py weekly [--dry-run]   # next plan for every user without one this week

Run `weekly` once a week (for example from cron on Monday), after progress_forecast.py weekly.
"""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import uuid

import exercise_ranker
from exercise_ranker import fetch_all
from progress_forecast import to_date, week_start

BASE_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
recommender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recommender)

PROGRESS_RATE = 0.9
REPEAT_RATE = 0.6
REP_STEP = 2
CARDIO_STEP = 5  # minutes
STRETCH_SETS = (2, 4)  # "2-4 times" per stretch (ACSM)
STATUS_RANK = {"skipped": 0, "partial": 1, "completed": 2}
# Supabase allows large inserts, but smaller ones fail more gracefully.
INSERT_CHUNK = 500


def parse_range(text):
    """(low, high) from "1-3" or "3"."""
    low, _, high = text.partition("-")
    return int(low), int(high or low)


def dose_bounds(profile, exercise, days):
    """{"sets": (lo, hi) | None, "reps": ..., "minutes": ...} for one exercise in a days-day week."""
    group = recommender.age_group(profile["age"])
    level = profile["fitness_level"]
    category = exercise["category"]
    if category == "stretching":
        return {"sets": STRETCH_SETS, "reps": None, "minutes": None}
    if category == "cardio":
        if group == "youth":
            return {"sets": None, "reps": None, "minutes": (60, 60)}
        _, low, high = recommender.CARDIO_WEEKLY[level]
        minutes = (recommender.session_minutes(low, days), recommender.session_minutes(high, days))
        return {"sets": None, "reps": None, "minutes": minutes}
    table = recommender.PLYOMETRIC_DOSE if category == "plyometrics" else recommender.STRENGTH_DOSE
    sets, reps = table[group][level]
    return {"sets": parse_range(sets), "reps": parse_range(reps), "minutes": None}


def clamp(dose, bounds):
    return {key: None if bounds[key] is None else
            min(max(dose[key] if dose.get(key) is not None else bounds[key][0], bounds[key][0]),
                bounds[key][1])
            for key in ("sets", "reps", "minutes")}


def starting_dose(bounds):
    return {key: None if value is None else value[0] for key, value in bounds.items()}


def step_up(dose, bounds):
    """Reps first, then a set with reps back at the bottom. Cardio adds minutes."""
    dose = dict(dose)
    if bounds["minutes"]:
        dose["minutes"] = min(dose["minutes"] + CARDIO_STEP, bounds["minutes"][1])
    elif bounds["reps"] and dose["reps"] < bounds["reps"][1]:
        dose["reps"] = min(dose["reps"] + REP_STEP, bounds["reps"][1])
    elif dose["sets"] < bounds["sets"][1]:
        dose["sets"] += 1
        if bounds["reps"]:
            dose["reps"] = bounds["reps"][0]
    return dose


def step_down(dose, bounds):
    """A set first, then reps. Cardio drops minutes."""
    dose = dict(dose)
    if bounds["minutes"]:
        dose["minutes"] = max(dose["minutes"] - CARDIO_STEP, bounds["minutes"][0])
    elif dose["sets"] > bounds["sets"][0]:
        dose["sets"] -= 1
    elif bounds["reps"]:
        dose["reps"] = max(dose["reps"] - REP_STEP, bounds["reps"][0])
    return dose


def ranked_groups(profile, exercises, model=None):
    """Every allowed exercise per muscle group, best first."""
    return recommender.recommend_exercises(profile, exercises, model, per_group=None)


def first_week(profile, exercises, start, model=None):
    """Week-1 plan: the top PER_GROUP exercises per group, rotated over workout_frequency days."""
    days = profile["workout_frequency"]
    rotations = {group: matches[:recommender.PER_GROUP]
                 for group, matches in ranked_groups(profile, exercises, model).items()}
    return assemble(profile, start, days, rotations, {})


def assemble(profile, start, days, rotations, doses):
    """Day d takes the ((d - 1) mod n)th exercise of each group's rotation.

    doses maps exercise id to its dose; missing ones start at the bottom of the range.
    """
    items = []
    for day in range(1, days + 1):
        for group, rotation in rotations.items():
            if not rotation:
                continue
            exercise = rotation[(day - 1) % len(rotation)]
            bounds = dose_bounds(profile, exercise, days)
            dose = clamp(doses[exercise["id"]], bounds) if exercise["id"] in doses else starting_dose(bounds)
            items.append({"day": day, "group": group, "exercise": exercise, **dose})
    return {"week_start": start, "days": days, "items": items}


def day_statuses(plan, logs):
    """{day: best completion_status logged for it}. Unlogged days count as skipped."""
    statuses = {day: "skipped" for day in range(1, plan["days"] + 1)}
    for log in logs:
        day = log.get("day_number")
        if day in statuses and STATUS_RANK[log["completion_status"]] > STATUS_RANK[statuses[day]]:
            statuses[day] = log["completion_status"]
    return statuses


def completion_rate(plan, logs):
    statuses = day_statuses(plan, logs).values()
    done = sum(1.0 if s == "completed" else 0.5 if s == "partial" else 0.0 for s in statuses)
    return done / plan["days"]


def next_week(profile, exercises, previous, logs, model=None):
    """The plan for the week after previous, adapted to the logs linked to previous."""
    statuses = day_statuses(previous, logs)
    rate = completion_rate(previous, logs)
    if rate >= PROGRESS_RATE and "skipped" not in statuses.values():
        trend, days = step_up, min(profile["workout_frequency"], previous["days"] + 1)
    elif rate >= REPEAT_RATE:
        trend, days = None, min(profile["workout_frequency"], previous["days"])
    else:
        did = sum(1 for s in statuses.values() if s != "skipped")
        trend, days = step_down, max(1, min(profile["workout_frequency"], did + 1))

    ranked = ranked_groups(profile, exercises, model)
    rotations, doses = {}, {}
    for group, matches in ranked.items():
        allowed = {e["id"] for e in matches}
        # Last week's exercises for this group in day order, with the days each one was on.
        kept = {}
        for item in previous["items"]:
            if item["group"] == group and item["exercise"]["id"] in allowed:
                kept.setdefault(item["exercise"]["id"], (item, []))[1].append(statuses[item["day"]])
        used = set(kept)
        spare = (e for e in matches if e["id"] not in used)
        rotation = []
        for item, seen in kept.values():
            exercise = item["exercise"]
            bounds = dose_bounds(profile, exercise, days)
            dose = clamp(item, bounds)
            if all(s == "skipped" for s in seen):
                exercise = next(spare, exercise)
                if exercise is not item["exercise"]:
                    rotation.append(exercise)  # new exercise starts at the bottom of its range
                    continue
            if any(s != "completed" for s in seen):
                dose = step_down(dose, bounds)
            elif trend:
                dose = trend(dose, bounds)
            doses[exercise["id"]] = dose
            rotation.append(exercise)
        # A group that is new (or emptied by a profile change) starts like week 1.
        while len(rotation) < recommender.PER_GROUP and (exercise := next(spare, None)):
            rotation.append(exercise)
        rotations[group] = rotation
    return assemble(profile, previous["week_start"] + timedelta(days=7), days, rotations, doses)


def dose_text(profile, item):
    """How the dose reads in the workout, matching prescribe()."""
    category = item["exercise"]["category"]
    if category == "stretching":
        return f"hold {recommender.STRETCH_HOLD[recommender.age_group(profile['age'])]}, {item['sets']} times"
    if category == "cardio":
        if recommender.age_group(profile["age"]) == "youth":
            return recommender.prescribe(profile, item["exercise"])
        effort = recommender.CARDIO_WEEKLY[profile["fitness_level"]][0]
        return f"{item['minutes']} min {effort} effort"
    return f"{item['sets']} {'set' if item['sets'] == 1 else 'sets'} x {item['reps']} reps"


def format_plan(profile, plan):
    lines = [f"\n========== FIT-SENSE WEEK OF {plan['week_start']} ==========",
             f"{profile['name']} | Age {profile['age']} | {profile['points']} points",
             f"Level: {profile['fitness_level']} | Goal: {profile['fitness_goal']} | "
             f"Location: {profile['workout_location']} | {plan['days']} days this week",
             f"Saved equipment: {', '.join(profile['equipment']) or 'none'}"]
    for day in range(1, plan["days"] + 1):
        lines.append(f"\n--- Day {day} ---")
        for item in plan["items"]:
            if item["day"] == day:
                exercise = item["exercise"]
                lines.append(f"- [{item['group']}] {exercise['name']} ({exercise['level']}, "
                             f"{exercise['equipment'] or 'no equipment'}): {dose_text(profile, item)}")
    if not plan["items"]:
        lines.append("No matching exercises. Add equipment in user_preferences or change the goal.")
    return "\n".join(lines)


# ---------- Supabase ----------

# The exercises table only takes the profile's workout_preferences values as workout_type, and
# beginner/intermediate/advanced as difficulty (its check constraints).
WORKOUT_TYPES = {"strength": "strength", "powerlifting": "strength", "olympic weightlifting": "strength",
                 "strongman": "strength", "cardio": "cardio", "plyometrics": "hiit", "stretching": "yoga"}
DIFFICULTY = {"expert": "advanced"}

def exercise_row(exercise):
    return {"name": exercise["name"], "muscle_group": recommender.muscle_group(exercise),
            "difficulty": DIFFICULTY.get(exercise["level"], exercise["level"]), "equipment": exercise["equipment"],
            "workout_type": WORKOUT_TYPES[exercise["category"]],
            "instructions": "\n".join(exercise["instructions"])}


def sync_exercises(client, exercises, dry_run=False):
    """Add the JSON exercises missing from the exercises table. Returns ({name: id}, rows added)."""
    ids = {row["name"].strip().lower(): row["exercise_id"]
           for row in fetch_all(client, "exercises", "exercise_id, name", "exercise_id")}
    new = []
    for exercise in exercises["home"] + exercises["gym"]:
        key = exercise["name"].strip().lower()
        if key not in ids:
            ids[key] = str(uuid.uuid4())
            new.append({"exercise_id": ids[key], **exercise_row(exercise)})
    if not dry_run:
        insert(client, "exercises", new)
    return ids, new


def insert(client, table, rows):
    for i in range(0, len(rows), INSERT_CHUNK):
        client.table(table).insert(rows[i:i + INSERT_CHUNK]).execute()


def plan_rows(user_id, profile, plan, exercise_ids):
    """(workout_plans row, plan_exercises rows). IDs are made here so the caller knows them."""
    plan_id = str(uuid.uuid4())
    plan_row = {"plan_id": plan_id, "user_id": user_id, "plan_name": f"Week of {plan['week_start']}",
                "fitness_goal": profile["fitness_goal"], "days_per_week": plan["days"],
                "week_start": plan["week_start"].isoformat()}
    exercise_rows = [{"plan_exercise_id": str(uuid.uuid4()), "plan_id": plan_id,
                      "exercise_id": exercise_ids[item["exercise"]["name"].strip().lower()],
                      "day_number": item["day"], "sets": item["sets"], "reps": item["reps"],
                      "duration_minutes": item["minutes"]}
                     for item in plan["items"]]
    return plan_row, exercise_rows


def load_plans(client, exercises, user_id=None):
    """{user_id: [(plan_id, plan)]} oldest first, rebuilt from workout_plans and plan_exercises."""
    by_name = {e["name"].strip().lower(): e for e in exercises["home"] + exercises["gym"]}
    plans = {}
    for row in fetch_all(client, "workout_plans", "plan_id, user_id, days_per_week, week_start",
                         "plan_id", user_id):
        if row["week_start"]:
            plans[row["plan_id"]] = (row["user_id"], {"week_start": to_date(row["week_start"]),
                                                      "days": row["days_per_week"], "items": []})
    for row in fetch_all(client, "plan_exercises",
                         "plan_exercise_id, plan_id, day_number, sets, reps, duration_minutes, exercises(name)",
                         "plan_exercise_id"):
        exercise = by_name.get(((row.get("exercises") or {}).get("name") or "").strip().lower())
        if row["plan_id"] in plans and exercise:
            plans[row["plan_id"]][1]["items"].append(
                {"day": row["day_number"], "group": recommender.muscle_group(exercise), "exercise": exercise,
                 "sets": row["sets"], "reps": row["reps"], "minutes": row["duration_minutes"]})
    result = {}
    for plan_id, (owner, plan) in sorted(plans.items(), key=lambda pair: pair[1][1]["week_start"]):
        plan["items"].sort(key=lambda item: item["day"])
        result.setdefault(owner, []).append((plan_id, plan))
    return result


def plan_for_week(profile, exercises, saved, logs, start, model=None):
    """This week's plan from the user's saved plans: week 1 if none, else adapted from the latest."""
    earlier = [(plan_id, plan) for plan_id, plan in saved if plan["week_start"] < start]
    if not earlier:
        return first_week(profile, exercises, start, model)
    plan_id, previous = earlier[-1]
    plan = next_week(profile, exercises, previous, [log for log in logs if log["plan_id"] == plan_id], model)
    return {**plan, "week_start": start}


def current_plan(client, profile, exercises, today=None, model=None):
    """This week's saved plan for one user, building and saving it first if there is none."""
    today = today or datetime.now(timezone.utc).date()
    start = week_start(today)
    saved = load_plans(client, exercises, profile["user_id"]).get(profile["user_id"], [])
    for _, plan in saved:
        if plan["week_start"] == start:
            return plan
    logs = fetch_all(client, "workout_logs", "workout_log_id, plan_id, day_number, completion_status",
                     "workout_log_id", profile["user_id"])
    plan = plan_for_week(profile, exercises, saved, logs, start, model)
    ids, _ = sync_exercises(client, exercises)
    plan_row, exercise_rows = plan_rows(profile["user_id"], profile, plan, ids)
    client.table("workout_plans").insert(plan_row).execute()
    insert(client, "plan_exercises", exercise_rows)
    return plan


def run_weekly(client, today=None, dry_run=False):
    """Save this week's plan for every user who has none yet. Returns the workout_plans rows."""
    today = today or datetime.now(timezone.utc).date()
    start = week_start(today)
    exercises = recommender.load_exercises()
    model = exercise_ranker.load_model()
    saved = load_plans(client, exercises)
    logs = {}
    for log in fetch_all(client, "workout_logs", "workout_log_id, user_id, plan_id, day_number, completion_status",
                         "workout_log_id"):
        logs.setdefault(log["user_id"], []).append(log)
    ids, _ = sync_exercises(client, exercises, dry_run)
    plans, items = [], []
    for row in fetch_all(client, "profiles",
                         "*, user_preferences(available_equipment), user_gamification(total_xp)", "user_id"):
        profile = recommender.profile_from_supabase_row(row)
        user_plans = saved.get(profile["user_id"], [])
        if any(plan["week_start"] == start for _, plan in user_plans):
            continue
        plan = plan_for_week(profile, exercises, user_plans, logs.get(profile["user_id"], []), start, model)
        plan_row, exercise_rows = plan_rows(profile["user_id"], profile, plan, ids)
        plans.append(plan_row)
        items += exercise_rows
    if not dry_run:
        insert(client, "workout_plans", plans)
        insert(client, "plan_exercises", items)
    return plans


def main():
    if sys.argv[1:2] == ["weekly"]:
        dry_run = "--dry-run" in sys.argv
        plans = run_weekly(recommender.supabase_client(), dry_run=dry_run)
        print(f"{'Would save' if dry_run else 'Saved'} {len(plans)} plans to workout_plans.")
    else:
        print("Usage: python weekly_plan.py weekly [--dry-run]")


if __name__ == "__main__":
    main()
