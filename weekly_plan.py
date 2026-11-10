"""Weekly workout plans saved to Supabase, adapted each week to how the user did last week.

Week 1 comes from the profile: the recommender's exercises spread over workout_frequency days,
each dose at the bottom of its guideline range (see dose_range() in Fitsense-Issue-5.py). From
week 2 on, the plan is rebuilt from last week's plan and the workout_logs linked to it
(plan_id + day_number). Completion = (completed days + half the partial days) / planned days:

- at least PROGRESS_RATE with no skipped day: one step up in dose, and one more day (up to
  workout_frequency) if a reduced week came before
- at least REPEAT_RATE: same dose
- below that: one more day than they did (up to workout_frequency), one step down in dose

The week's decision comes from adaptive_week_two.py:
- Swap-aware: a day skipped because the equipment or location wasn't available (workout_logs
  skip_reason 'no_equipment' or 'location') isn't counted as missed, and its exercises are kept.
- If models/adaptive_week_two.json exists (python adaptive_week_two.py), XGBoost picks between
  the rule's choice and one step either side; without it, the swap-aware rule decides alone.
Each new plan records the decision in plan["adaptation"], which format_plan prints.

On top of that, an exercise that was only on skipped days is swapped for the next-ranked one in
its group, and one on a partial or skipped day steps down. Doses never leave the guideline range.

Every week keeps at least one recovery day (MAX_TRAINING_DAYS = 6). week_schedule() places the
training days on the calendar with recovery days between them where the week allows (ACSM: about
48 h before training the same muscles again), and a recovery day gets an optional light routine:
an easy walk and a few beginner stretches (recovery_routine()).

    python weekly_plan.py weekly [--dry-run]   # next plan for every user without one this week
    python weekly_plan.py swap <user_id> --without barbell [--save]   # same-day swaps (see adaptive_week_two.py)

Run `weekly` once a week (for example from cron on Monday), after progress_forecast.py weekly.
"""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import uuid

import adaptive_week_two
import exercise_ranker
from exercise_ranker import fetch_all
from progress_forecast import to_date, week_start

BASE_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
recommender = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(recommender)

# The thresholds live in adaptive_week_two.py so the rule and the model use the same numbers.
PROGRESS_RATE = adaptive_week_two.PROGRESS_RATE
REPEAT_RATE = adaptive_week_two.REPEAT_RATE
REP_STEP = 2
CARDIO_STEP = 5  # minutes
STATUS_RANK = {"skipped": 0, "partial": 1, "completed": 2}
# Supabase allows large inserts, but smaller ones fail more gracefully.
INSERT_CHUNK = 500
# At least one full recovery day a week, even for a 7-day workout_frequency.
MAX_TRAINING_DAYS = 6
RECOVERY_WALK = "20-30 min easy walk"
# One stretch per area, for the muscles the training days work.
RECOVERY_AREAS = ("Lower Body", "Upper Body", "Core")
RECOVERY_EQUIPMENT = {None, "body only", "foam roll"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


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


def training_days(profile):
    """Most training days a week for this profile: workout_frequency, leaving a recovery day."""
    return min(profile["workout_frequency"], MAX_TRAINING_DAYS)


def ranked_groups(profile, exercises, model=None):
    """Every allowed exercise per muscle group, best first."""
    return recommender.recommend_exercises(profile, exercises, model, per_group=None)


def first_week(profile, exercises, start, model=None):
    """Week-1 plan: the top PER_GROUP exercises per group, rotated over the training days."""
    days = training_days(profile)
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
            bounds = recommender.dose_range(profile, exercise, days)
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


def adaptation_details(profile, previous, logs, adapt_model=None):
    """How next week is decided: {"decision", "days", "rule", "original_rule", "source", ...}.

    "rule" is the swap-aware rule, "original_rule" the rule before swaps were taken into account,
    and "source" says whether the XGBoost adaptation model or the rule made the decision. Days
    never go above training_days(profile), so every week keeps a recovery day.
    """
    state = adaptive_week_two.state_from_plan(profile, previous, logs)
    return adaptive_week_two.decide(state, adapt_model)


def adaptation(profile, previous, logs, adapt_model=None):
    """("progress" | "same dose" | "reduce", days next week) from last week's completion."""
    details = adaptation_details(profile, previous, logs, adapt_model)
    return details["decision"], details["days"]


def next_week(profile, exercises, previous, logs, model=None, adapt_model=None):
    """The plan for the week after previous, adapted to the logs linked to previous.

    model is the exercise ranker (exercise order); adapt_model is the XGBoost adaptation model
    (progress / same dose / reduce). Either can be None, and the rules take over.
    """
    details = adaptation_details(profile, previous, logs, adapt_model)
    change, days = details["decision"], details["days"]
    statuses = day_statuses(previous, logs)
    for day in details["equipment_skips"]:
        statuses[day] = "completed"  # blocked by equipment, not by the user: keep its exercises
    trend = {"progress": step_up, "same dose": None, "reduce": step_down}[change]

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
            bounds = recommender.dose_range(profile, exercise, days)
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
    plan = assemble(profile, previous["week_start"] + timedelta(days=7), days, rotations, doses)
    plan["adaptation"] = details
    return plan


def spread(count, slots):
    """Which of `slots` consecutive days (0-based) get `count` sessions, spaced as evenly as possible.

    Up to every other day, sessions get a recovery day between them (3 in 7 -> Mon Wed Fri);
    beyond that, the recovery days are spread out instead, the last day always one so the week
    doesn't run into next week's first session (5 in 7 -> rest Thu and Sun).
    """
    if count <= 0:
        return []
    if count >= slots:
        return list(range(slots))
    if count <= (slots + 1) // 2:
        step = max(2.0, slots / count)
        return [int(i * step) for i in range(count)]
    rest = slots - count
    resting = {slots - 1 - int(j * slots / rest) for j in range(rest)}
    return [i for i in range(slots) if i not in resting]


def week_schedule(start, days, logged, today):
    """The week as 7 entries {date, weekday, kind: "training" | "recovery", day}.

    logged maps a plan day to the date it was logged on. Past days show what happened (a day with
    no plan workout was a recovery day); the plan days still open are spread over today..Sunday,
    leaving a recovery day after yesterday's workout when there's room.
    """
    dates = [start + timedelta(days=i) for i in range(7)]
    on_date = {}
    for day, logged_on in sorted(logged.items()):
        on_date.setdefault(logged_on, day)
    open_days = [day for day in range(1, days + 1) if day not in logged]
    free = [d for d in dates if d >= today and d not in on_date]
    if free and (free[0] - timedelta(days=1)) in on_date and len(open_days) <= len(free) // 2:
        free = free[1:]
    placed = {free[i]: day for i, day in zip(spread(len(open_days), len(free)), open_days)}
    schedule = []
    for d in dates:
        day = on_date.get(d) or placed.get(d)
        schedule.append({"date": d, "weekday": WEEKDAYS[d.weekday()],
                         "kind": "training" if day else "recovery", "day": day})
    return schedule


def recovery_routine(profile, exercises):
    """A light, optional recovery-day routine: an easy walk and one beginner stretch per area."""
    stretches = [e for e in recommender.candidate_exercises(profile, exercises)
                 if e["category"] == "stretching" and e["level"] == "beginner" and e["equipment"] in RECOVERY_EQUIPMENT]
    stretches.sort(key=lambda e: ("stretch" not in e["name"].lower(), e["name"]))  # holds before drills
    routine = []
    for area in RECOVERY_AREAS:
        muscles = recommender.MUSCLE_GROUPS[area]
        match = next((e for e in stretches if set(e["primaryMuscles"]) & muscles and e not in routine), None)
        if match:
            routine.append(match)
    bounds = recommender.dose_range(profile, {"category": "stretching"}, 1)
    return {"walk": RECOVERY_WALK,
            "stretches": [{"day": 0, "group": "Mobility", "exercise": e, **starting_dose(bounds)} for e in routine]}


def dose_text(profile, item):
    """How the dose reads in the workout, e.g. "2 sets x 10 reps" or "30 min moderate effort"."""
    category = item["exercise"]["category"]
    group = recommender.age_group(profile["age"])
    if category == "stretching":
        return f"hold {recommender.STRETCH_HOLD[group]}, {item['sets']} times"
    if category == "cardio":
        effort = "moderate-to-vigorous" if group == "youth" else recommender.CARDIO_WEEKLY[profile["fitness_level"]][0]
        return f"{item['minutes']} min {effort} effort"
    return f"{item['sets']} {'set' if item['sets'] == 1 else 'sets'} x {item['reps']} reps"


def adaptation_text(details):
    """One line on how this week was decided, e.g. "Adapted: progress (XGBoost; rule said same dose)"."""
    source = "XGBoost adaptation model" if details["source"] == "xgboost" else "swap-aware rule"
    notes = []
    if details["source"] == "xgboost" and details["rule"] != details["decision"]:
        notes.append(f"rule said {details['rule']}")
    if details["original_rule"] != details["rule"]:
        notes.append(f"before swap-awareness: {details['original_rule']}")
    if details["equipment_skips"]:
        notes.append("equipment-blocked day " + ", ".join(str(d) for d in sorted(details["equipment_skips"]))
                     + " not counted as missed")
    return (f"Adapted from last week: {details['decision']} ({source}"
            + ("; " + "; ".join(notes) if notes else "") + ")")


def format_plan(profile, plan, exercises=None):
    lines = [f"\n========== FIT-SENSE WEEK OF {plan['week_start']} ==========",
             f"{profile['name']} | Age {profile['age']} | {profile['points']} points",
             f"Level: {profile['fitness_level']} | Goal: {profile['fitness_goal']} | "
             f"Location: {profile['workout_location']} | {plan['days']} {'day' if plan['days'] == 1 else 'days'} this week",
             f"Saved equipment: {', '.join(profile['equipment']) or 'none'}"]
    if plan.get("adaptation"):
        lines.append(adaptation_text(plan["adaptation"]))
    for day in range(1, plan["days"] + 1):
        lines.append(f"\n--- Day {day} ---")
        for item in plan["items"]:
            if item["day"] == day:
                exercise = item["exercise"]
                lines.append(f"- [{item['group']}] {exercise['name']} ({exercise['level']}, "
                             f"{exercise['equipment'] or 'no equipment'}): {dose_text(profile, item)}")
    if not plan["items"]:
        lines.append("No matching exercises. Add equipment in user_preferences or change the goal.")
    schedule = week_schedule(plan["week_start"], plan["days"], {}, plan["week_start"])
    lines.append("\nSchedule: " + ", ".join(f"{e['weekday']} {'Day ' + str(e['day']) if e['day'] else 'recovery'}"
                                           for e in schedule))
    if exercises:
        routine = recovery_routine(profile, exercises)
        lines.append(f"--- Recovery days (optional) ---\n- {routine['walk']}")
        lines += [f"- {item['exercise']['name']}: {dose_text(profile, item)}" for item in routine["stretches"]]
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


LOG_COLUMNS = "workout_log_id, user_id, plan_id, day_number, completion_status"
SWAP_LOG_COLUMNS = ", skip_reason, swapped"  # optional columns, see adaptive_week_two.py


def fetch_logs(client, user_id=None):
    """workout_logs rows, with skip_reason and swapped when those optional columns exist."""
    try:
        return fetch_all(client, "workout_logs", LOG_COLUMNS + SWAP_LOG_COLUMNS, "workout_log_id", user_id)
    except Exception:
        return fetch_all(client, "workout_logs", LOG_COLUMNS, "workout_log_id", user_id)


def plan_for_week(profile, exercises, saved, logs, start, model=None, adapt_model=None):
    """This week's plan from the user's saved plans: week 1 if none, else adapted from the latest."""
    earlier = [(plan_id, plan) for plan_id, plan in saved if plan["week_start"] < start]
    if not earlier:
        return first_week(profile, exercises, start, model)
    plan_id, previous = earlier[-1]
    plan = next_week(profile, exercises, previous, [log for log in logs if log["plan_id"] == plan_id],
                     model, adapt_model)
    return {**plan, "week_start": start}


def current_plan(client, profile, exercises, today=None, model=None, adapt_model="saved"):
    """This week's saved plan for one user, building and saving it first if there is none.

    adapt_model "saved" loads models/adaptive_week_two.json if it exists; pass None for rules only.
    """
    today = today or datetime.now(timezone.utc).date()
    start = week_start(today)
    saved = load_plans(client, exercises, profile["user_id"]).get(profile["user_id"], [])
    for _, plan in saved:
        if plan["week_start"] == start:
            return plan
    if adapt_model == "saved":
        adapt_model = adaptive_week_two.load_model()
    logs = fetch_logs(client, profile["user_id"])
    plan = plan_for_week(profile, exercises, saved, logs, start, model, adapt_model)
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
    adapt_model = adaptive_week_two.load_model()
    saved = load_plans(client, exercises)
    logs = {}
    for log in fetch_logs(client):
        logs.setdefault(log["user_id"], []).append(log)
    ids, _ = sync_exercises(client, exercises, dry_run)
    plans, items = [], []
    for row in fetch_all(client, "profiles",
                         "*, user_preferences(available_equipment), user_gamification(total_xp)", "user_id"):
        profile = recommender.profile_from_supabase_row(row)
        user_plans = saved.get(profile["user_id"], [])
        if any(plan["week_start"] == start for _, plan in user_plans):
            continue
        plan = plan_for_week(profile, exercises, user_plans, logs.get(profile["user_id"], []), start, model,
                             adapt_model)
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
    elif sys.argv[1:2] == ["swap"]:
        adaptive_week_two.main_swap(sys.argv[2:])
    else:
        print("Usage: python weekly_plan.py weekly [--dry-run]\n"
              "       python weekly_plan.py swap <user_id> --without barbell [--save]")


if __name__ == "__main__":
    main()
