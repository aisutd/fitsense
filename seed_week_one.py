"""Give the 200 Supabase test users a saved week-1 plan, link their week-1 logs, and plan week 2.

Week 1 is each user's own first logged Monday-Sunday week. Its logs get plan_id, and day_number
by order (their first log that week is day 1). Logs past the plan's last day keep day_number
null, and logs from later weeks are left alone. Week 2 is adapted from week 1 (weekly_plan.py).
Test users with no logs get a week-1 plan for the current week and no week 2.

    python seed_week_one.py --dry-run   # counts only, writes nothing
    python seed_week_one.py             # write; IDs go to UNDO_PATH first
    python seed_week_one.py --undo      # delete the seeded plans and unlink the logs

Needs backend/sql/002_weekly_plans.sql to have been run. Exercises added to the exercises table
are shared, so --undo keeps them.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import weekly_plan
from exercise_ranker import fetch_all
from progress_forecast import to_date, week_start
from weekly_plan import recommender

BASE_DIR = Path(__file__).resolve().parent
UNDO_PATH = BASE_DIR / "seed_week_one.ids.json"
# The test users were created in one batch; nothing else was created in this window.
TEST_USERS_CREATED = ("2026-10-23T18:51", "2026-10-23T18:56")
TEST_USER_COUNT = 200
UNDO_CHUNK = 100  # IDs per in_() filter, to keep request URLs short


def test_profiles(client):
    rows = fetch_all(client, "profiles",
                     "*, user_preferences(available_equipment), user_gamification(total_xp)", "user_id")
    low, high = TEST_USERS_CREATED
    return [recommender.profile_from_supabase_row(row) for row in rows if low <= row["created_at"] < high]


def seed(client, today=None):
    """(workout_plans rows, plan_exercises rows, log updates, new exercise rows, summary) to write."""
    today = today or datetime.now(timezone.utc).date()
    exercises = recommender.load_exercises()
    profiles = test_profiles(client)
    if len(profiles) != TEST_USER_COUNT:
        raise RuntimeError(f"Expected {TEST_USER_COUNT} test users, found {len(profiles)}. Check TEST_USERS_CREATED.")
    ids = {profile["user_id"] for profile in profiles}
    logs = {}
    for log in fetch_all(client, "workout_logs", "workout_log_id, user_id, plan_id, workout_date, completion_status",
                         "workout_log_id"):
        if log["user_id"] in ids:
            logs.setdefault(log["user_id"], []).append(log)
    if any(log["plan_id"] for user_logs in logs.values() for log in user_logs):
        raise RuntimeError("Some test-user logs already have a plan_id. Run --undo first, or seed by hand.")
    exercise_ids, new_exercises = weekly_plan.sync_exercises(client, exercises, dry_run=True)

    plans, items, updates = [], [], []
    summary = Counter()
    for profile in profiles:
        user_logs = sorted(logs.get(profile["user_id"], []), key=lambda log: (log["workout_date"], log["workout_log_id"]))
        if not user_logs:
            plan = weekly_plan.first_week(profile, exercises, week_start(today))
            plan_row, rows = weekly_plan.plan_rows(profile["user_id"], profile, plan, exercise_ids)
            plans.append(plan_row)
            items += rows
            summary["users without logs"] += 1
            continue
        start = week_start(to_date(user_logs[0]["workout_date"]))
        summary[f"week 1 = week of {start}"] += 1
        week_one = weekly_plan.first_week(profile, exercises, start)
        plan_row, rows = weekly_plan.plan_rows(profile["user_id"], profile, week_one, exercise_ids)
        plans.append(plan_row)
        items += rows
        linked = []
        for index, log in enumerate(l for l in user_logs if week_start(to_date(l["workout_date"])) == start):
            day = index + 1 if index < week_one["days"] else None
            linked.append({**log, "plan_id": plan_row["plan_id"], "day_number": day})
            updates.append({"workout_log_id": log["workout_log_id"], "plan_id": plan_row["plan_id"],
                            "day_number": day})
        summary["week-1 logs past the plan's last day"] += sum(1 for log in linked if log["day_number"] is None)
        rate = weekly_plan.completion_rate(week_one, linked)
        week_two = weekly_plan.next_week(profile, exercises, week_one, linked)
        summary["week 2: " + ("progress" if rate >= weekly_plan.PROGRESS_RATE and
                              "skipped" not in weekly_plan.day_statuses(week_one, linked).values()
                              else "same dose" if rate >= weekly_plan.REPEAT_RATE else "reduce")] += 1
        summary["week 2 days changed"] += week_two["days"] != week_one["days"]
        plan_row, rows = weekly_plan.plan_rows(profile["user_id"], profile, week_two, exercise_ids)
        plans.append(plan_row)
        items += rows
    summary["later logs left unlinked"] = sum(len(v) for v in logs.values()) - len(updates)
    return plans, items, updates, new_exercises, summary


def migrated(client):
    """Whether backend/sql/002_weekly_plans.sql has been run."""
    try:
        client.table("workout_plans").select("week_start").limit(1).execute()
        client.table("workout_logs").select("day_number").limit(1).execute()
    except Exception:
        return False
    return True


def write(client, plans, items, updates, new_exercises):
    # IDs are saved before anything is written, so a run that stops halfway can still be undone.
    UNDO_PATH.write_text(json.dumps({"plans": [p["plan_id"] for p in plans],
                                     "logs": [u["workout_log_id"] for u in updates]}, indent=1))
    weekly_plan.insert(client, "exercises", new_exercises)
    weekly_plan.insert(client, "workout_plans", plans)
    weekly_plan.insert(client, "plan_exercises", items)
    for update in updates:
        (client.table("workout_logs")
         .update({"plan_id": update["plan_id"], "day_number": update["day_number"]})
         .eq("workout_log_id", update["workout_log_id"]).execute())


def undo(client):
    saved = json.loads(UNDO_PATH.read_text())
    for i in range(0, len(saved["logs"]), UNDO_CHUNK):
        (client.table("workout_logs").update({"plan_id": None, "day_number": None})
         .in_("workout_log_id", saved["logs"][i:i + UNDO_CHUNK]).execute())
    for i in range(0, len(saved["plans"]), UNDO_CHUNK):
        chunk = saved["plans"][i:i + UNDO_CHUNK]
        client.table("plan_exercises").delete().in_("plan_id", chunk).execute()
        client.table("workout_plans").delete().in_("plan_id", chunk).execute()
    UNDO_PATH.unlink()
    return saved


def main():
    client = recommender.supabase_client()
    if "--undo" in sys.argv:
        saved = undo(client)
        print(f"Deleted {len(saved['plans'])} plans and unlinked {len(saved['logs'])} logs.")
        return
    if UNDO_PATH.exists() and "--dry-run" not in sys.argv:
        print(f"{UNDO_PATH.name} exists: the seed already ran. Run --undo first.")
        return
    if "--dry-run" not in sys.argv and not migrated(client):
        print("Run backend/sql/002_weekly_plans.sql in the Supabase SQL editor first.")
        return
    plans, items, updates, new_exercises, summary = seed(client)
    dry_run = "--dry-run" in sys.argv
    if not dry_run:
        write(client, plans, items, updates, new_exercises)
    verb = "Would add" if dry_run else "Added"
    print(f"{verb} {len(new_exercises)} exercises, {len(plans)} workout_plans, {len(items)} plan_exercises; "
          f"{'would link' if dry_run else 'linked'} {len(updates)} workout_logs.")
    for key, count in sorted(summary.items()):
        print(f"  {key}: {count}")
    if not dry_run:
        print(f"IDs saved to {UNDO_PATH.name} (python seed_week_one.py --undo to revert).")


if __name__ == "__main__":
    main()
