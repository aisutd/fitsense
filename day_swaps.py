"""Excuses and exercise swaps: when a player can't do a plan day as planned, swap what they can't do.

The player gives a reason (the equipment is broken or taken, or they can't make it to the gym) and
each exercise on the affected days that no longer fits is replaced with the closest one that does:
same muscle group, same category and muscles where possible, same movement type and level, not
already in the week, with the sets and reps already reached carried over. The change can be for
one day or the rest of the week's open days, and it's saved to the week's plan (plan_exercises), so
the plan stays swapped. The profile itself isn't changed.

Skips for these reasons (workout_logs.skip_reason 'no_equipment' or 'location', backend/sql/009)
are excused: weekly_plan.py, the HealthScore and the forecast don't count them as missed.

The swap logic is Lane's, from the league-banners branch (adaptive_week_two.py); the week-to-week
adaptation now lives in adaptation_model.py / weekly_plan.py.
"""

import exercise_ranker
import weekly_plan

recommender = weekly_plan.recommender

# Skip reasons that aren't about the player's effort: the day isn't counted as missed.
EXCUSED_REASONS = weekly_plan.EXCUSED_REASONS
LOCATIONS = ("home", "gym", "outdoors", "mixed")


def todays_profile(profile, today):
    """The profile as it applies today: location and equipment overridden for today only."""
    changed = dict(profile)
    if today.get("location"):
        changed["workout_location"] = today["location"]
    if today.get("equipment") is not None:
        changed["equipment"] = sorted(today["equipment"])
    return changed


def allowed_today(profile, today, exercises):
    """{muscle group: [allowed exercises, rule order]} for today's conditions."""
    groups = recommender.recommend_exercises(todays_profile(profile, today), exercises, None, per_group=None)
    without = {item.lower() for item in today.get("without") or []}
    return {group: [e for e in matches if (e["equipment"] or "").lower() not in without]
            for group, matches in groups.items()}


def similarity(original, candidate, in_week=frozenset()):
    """Sort key: higher is closer to the original exercise (and fresher for this week)."""
    a, b = set(original["primaryMuscles"]), set(candidate["primaryMuscles"])
    level_gap = abs(recommender.LEVEL_RANK[original["level"]] - recommender.LEVEL_RANK[candidate["level"]])
    return (candidate["category"] == original["category"], len(a & b) > 0, candidate["id"] not in in_week,
            len(a & b), candidate["force"] == original["force"], candidate["mechanic"] == original["mechanic"],
            -level_gap)


def substitute(profile, item, candidates, taken_today, in_week, ranker=None):
    """Closest allowed replacement for one plan item, or None if its group has nothing allowed.

    Order: same category and muscles, not already in the week, same movement type and level;
    the exercise ranker (if trained) only breaks ties, then the rule order.
    """
    original = item["exercise"]
    options = [e for e in candidates if e["id"] != original["id"] and e["id"] not in taken_today]
    if not options:
        return None
    rule_rank = {e["id"]: i for i, e in enumerate(candidates)}
    learned = dict(zip((e["id"] for e in options), exercise_ranker.scores(ranker, profile, options))) if ranker else {}
    return max(options, key=lambda e: (similarity(original, e, in_week), learned.get(e["id"], 0.0),
                                       -rule_rank[e["id"]]))


def unavailable_reason(exercise, today_profile, today):
    equipment = exercise["equipment"] or "no equipment"
    label = "special equipment" if equipment == "other" else equipment
    if equipment.lower() in {w.lower() for w in today.get("without") or []}:
        return f"no {label} today"
    where = {"outdoors": "outdoors", "home": "at home"}.get(today_profile["workout_location"],
                                                              f"at the {today_profile['workout_location']}")
    return f"needs {label}, not available {where} today"


def swap_days(profile, plan, days, today, exercises, force_names=(), ranker=None):
    """(new plan, swaps). Replaces items on the given days that today's conditions rule out.

    today: {"location", "equipment", "without"}. Each swap is {"day", "group", "old", "new",
    "new_item", "old_dose", "new_dose", "reason"}; "new" is None when no allowed alternative exists
    (the item is left as it was and flagged).
    """
    allowed = allowed_today(profile, today, exercises)
    allowed_ids = {e["id"] for matches in allowed.values() for e in matches}
    force = {name.strip().lower() for name in force_names}
    in_week = {item["exercise"]["id"] for item in plan["items"]}
    today_profile = todays_profile(profile, today)

    items, swaps = [], []
    for item in plan["items"]:
        exercise = item["exercise"]
        forced = exercise["name"].strip().lower() in force
        if item["day"] not in days or (exercise["id"] in allowed_ids and not forced):
            items.append(item)
            continue
        taken = {i["exercise"]["id"] for i in plan["items"] + items if i["day"] == item["day"]}
        new = substitute(today_profile, item, allowed.get(item["group"], []), taken, in_week, ranker)
        reason = "you asked to swap it" if forced else unavailable_reason(exercise, today_profile, today)
        swap = {"day": item["day"], "group": item["group"], "old": exercise, "new": new, "new_item": None,
                "old_dose": weekly_plan.dose_text(profile, item), "new_dose": None, "reason": reason}
        if new is None:
            items.append(item)
            swap["reason"] += "; no allowed alternative"
        else:
            bounds = recommender.dose_range(profile, new, plan["days"])
            new_item = {**item, "exercise": new, **weekly_plan.clamp(item, bounds)}  # progress carried over
            items.append(new_item)
            in_week.add(new["id"])
            swap.update(new_item=new_item, new_dose=weekly_plan.dose_text(profile, new_item))
        swaps.append(swap)
    return {**plan, "items": items}, swaps


def save_swaps(client, plan_id, swaps, exercises):
    """Update the swapped rows of plan_exercises in place. Returns how many rows changed."""
    ids, _ = weekly_plan.sync_exercises(client, exercises)  # adds any exercise the table is missing
    rows = (client.table("plan_exercises").select("plan_exercise_id, day_number, exercises(name)")
            .eq("plan_id", plan_id).execute().data)
    changed = 0
    for swap in swaps:
        if swap["new"] is None:
            continue
        old_name = swap["old"]["name"].strip().lower()
        row = next((r for r in rows if r["day_number"] == swap["day"]
                    and ((r.get("exercises") or {}).get("name") or "").strip().lower() == old_name), None)
        if row is None:
            continue
        item = swap["new_item"]
        (client.table("plan_exercises")
         .update({"exercise_id": ids[swap["new"]["name"].strip().lower()], "sets": item["sets"],
                  "reps": item["reps"], "duration_minutes": item["minutes"]})
         .eq("plan_exercise_id", row["plan_exercise_id"]).execute())
        rows.remove(row)
        changed += 1
    return changed
