"""Demo: one made-up sample user taken through five weeks of changes.

Nothing is read from or written to Supabase. It uses the same planning code as the app
(weekly_plan.py + Fitsense-Issue-5.py) and the trained ranker in models/exercise_ranker.json
if it exists, and shows where the ranker's choices differ from the rule-based order.

    python demo_sample_user.py

Edit SAMPLE_USER and WEEKS below to try your own scenarios.
"""

from datetime import date, timedelta

import adaptive_week_two
import exercise_ranker
import weekly_plan

recommender = weekly_plan.recommender

# ---------- The sample user (edit freely) ----------
SAMPLE_USER = {
    "user_id": "sample-user", "name": "Sam Sample", "age": 29, "points": 0,
    "fitness_level": "intermediate", "fitness_goal": "build_muscle",
    "workout_location": "gym", "workout_frequency": 4,
    "equipment": [], "workout_preferences": ["strength"],
}
FIRST_MONDAY = date(2026, 11, 2)

# Each week: what the user logged for the plan, and any profile change before the next plan.
WEEKS = [
    {"logs": ["completed", "completed", "completed", "completed"], "change": {},
     "story": "Week 1: completes every day"},
    {"logs": ["completed", "skipped", "partial", "completed"], "change": {},
     "story": "Week 2: misses a day and only half-finishes another"},
    {"logs": ["completed", "completed", "completed", "completed"],
     "change": {"workout_location": "home", "equipment": ["dumbbell", "bands"]},
     "story": "Week 3: completes every day, then moves to training at home with dumbbells and bands"},
    {"logs": ["skipped", "skipped", "completed", "skipped"], "change": {"workout_frequency": 3},
     "story": "Week 4: busy week (1 of 4 days), and lowers workout days to 3"},
    {"logs": ["completed", "completed"], "change": {},
     "story": "Week 5: completes both planned days"},
    {"logs": ["completed", "completed:swapped", "skipped:no_equipment"], "change": {},
     "story": "Week 6: swaps one day for missing equipment, and skips another because the gym was closed"},
]
# Log entries are "completed", "partial" or "skipped", optionally with a tag after a colon:
# "completed:swapped" (did a same-day swap) or "skipped:no_equipment" / "skipped:location".


def parse_log(day, text):
    """A workout_logs-like row from a WEEKS entry such as "skipped:no_equipment"."""
    status, _, tag = text.partition(":")
    log = {"day_number": day, "completion_status": status}
    if tag == "swapped":
        log["swapped"] = True
    elif tag:
        log["skip_reason"] = tag
    return log


def describe(profile, item):
    return f"{item['exercise']['name']} ({weekly_plan.dose_text(profile, item)})"


def changes_between(profile_before, before, profile_after, after):
    lines = []
    if before["days"] != after["days"]:
        lines.append(f"Days: {before['days']} -> {after['days']}")
    old = {(i["day"], i["group"]): i for i in before["items"]}
    new = {(i["day"], i["group"]): i for i in after["items"]}
    for day, group in sorted(set(old) | set(new)):
        a, b = old.get((day, group)), new.get((day, group))
        if a and not b:
            lines.append(f"Day {day} [{group}] removed: {describe(profile_before, a)}")
        elif b and not a:
            lines.append(f"Day {day} [{group}] added: {describe(profile_after, b)}")
        elif a["exercise"]["id"] != b["exercise"]["id"]:
            lines.append(f"Day {day} [{group}] swapped: {describe(profile_before, a)} -> {describe(profile_after, b)}")
        elif weekly_plan.dose_text(profile_before, a) != weekly_plan.dose_text(profile_after, b):
            lines.append(f"Day {day} [{group}] {a['exercise']['name']}: "
                         f"{weekly_plan.dose_text(profile_before, a)} -> {weekly_plan.dose_text(profile_after, b)}")
    return lines or ["No change."]


def ml_vs_rules(profile, exercises, model):
    """Top exercises per group: rule order vs the ranker's order, with the ranker's scores."""
    rules = recommender.recommend_exercises(profile, exercises, None)
    ranked = recommender.recommend_exercises(profile, exercises, model)
    print("\n  Ranker vs rules (top picks per muscle group):")
    for group in rules:
        rule_names = [e["name"] for e in rules[group]]
        scored = exercise_ranker.scores(model, profile, ranked[group])
        ml_names = [f"{e['name']} ({s:.2f})" for e, s in zip(ranked[group], scored)]
        same = "same" if rule_names == [e["name"] for e in ranked[group]] else "DIFFERENT"
        print(f"  [{group}] {same}")
        print(f"     rules : {', '.join(rule_names)}")
        print(f"     ranker: {', '.join(ml_names)}")


def plan_diff_without_model(profile, exercises, previous, logs, with_model, adapt_model=None):
    """Where this week's plan would differ if the ranker were off."""
    without = weekly_plan.next_week(profile, exercises, previous, logs, None, adapt_model) if previous \
        else weekly_plan.first_week(profile, exercises, FIRST_MONDAY, None)
    a = {(i["day"], i["group"]): i["exercise"]["name"] for i in without["items"]}
    b = {(i["day"], i["group"]): i["exercise"]["name"] for i in with_model["items"]}
    diffs = [f"Day {d} [{g}]: rules pick {a.get((d, g), '-')}, ranker picks {b.get((d, g), '-')}"
             for d, g in sorted(set(a) | set(b)) if a.get((d, g)) != b.get((d, g))]
    print("\n  Effect of the ranker on this plan: " + ("none (same exercises)" if not diffs else ""))
    for line in diffs:
        print("   - " + line)


def main():
    exercises = recommender.load_exercises()
    model = exercise_ranker.load_model()
    adapt_model = adaptive_week_two.load_model()
    print("Ranker:", "using models/exercise_ranker.json" if model
          else "none found, so exercise order is rule-based (run: python exercise_ranker.py train)")
    print("Adaptation:", "XGBoost, models/adaptive_week_two.json" if adapt_model
          else "swap-aware rule (run: python adaptive_week_two.py to train the model)")

    profile = dict(SAMPLE_USER)
    plan = weekly_plan.first_week(profile, exercises, FIRST_MONDAY, model)
    print("\n" + "#" * 70 + "\nWEEK 1 PLAN (built from the profile)")
    print(weekly_plan.format_plan(profile, plan))
    if model:
        ml_vs_rules(profile, exercises, model)
        plan_diff_without_model(profile, exercises, None, None, plan)

    for week_number, week in enumerate(WEEKS, start=1):
        logs = [parse_log(day, text) for day, text in enumerate(week["logs"][:plan["days"]], start=1)]
        new_profile = {**profile, **week["change"]}
        next_plan = weekly_plan.next_week(new_profile, exercises, plan, logs, model, adapt_model)
        details = next_plan["adaptation"]

        print("\n" + "#" * 70)
        print(f"{week['story']}")
        logged = ", ".join("day {} {}".format(l["day_number"], l["completion_status"])
                           + (" (swapped)" if l.get("swapped") else "")
                           + (f" ({l['skip_reason']})" if l.get("skip_reason") else "") for l in logs)
        print(f"  Logged: {logged}")
        print(f"  Completion {details['completion']:.0%} (equipment-blocked days left out)")
        print(f"  original rule: {details['original_rule']} | swap-aware rule: {details['rule']}"
              + (f" | XGBoost: {details['probabilities']}" if details["probabilities"] else ""))
        print(f"  -> decision: {details['decision']}, {details['days']} days next week ({details['source']})")
        if week["change"]:
            print("  Profile change: " + ", ".join(f"{k} {profile.get(k)!r} -> {v!r}" for k, v in week["change"].items()))
        print(f"\nWEEK {week_number + 1} PLAN")
        print(weekly_plan.format_plan(new_profile, next_plan))
        print("\n  What changed from last week:")
        for line in changes_between(profile, plan, new_profile, next_plan):
            print("   - " + line)
        if model:
            plan_diff_without_model(new_profile, exercises, plan, logs, next_plan, adapt_model)
        profile, plan = new_profile, next_plan

    print("\nDone. Nothing was saved to Supabase.")


if __name__ == "__main__":
    main()