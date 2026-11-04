"""Week-to-week adaptation with same-day exercise swaps.

Two parts that work together:

1. Same-day swaps. When the user says what's different today ("no barbell", "at home with
   dumbbells", "I can't do this one"), each exercise on today's plan that no longer fits is
   replaced right away with the closest allowed one (same muscle group and movement, progress
   kept). With --save the change is written to this week's plan in Supabase.

2. Next week's adaptation. Fixed rules decide what is LEGAL; XGBoost decides which legal move.
   - Rules: "progress" | "same dose" | "reduce", what each does to days and dose, a guard rail
     (the model may only pick the rule's choice or one step either side), dose bounds.
   - Swap-aware: a day skipped because equipment or the location wasn't available does not count
     as a missed workout, and a swapped day that was completed counts as completed.
   - XGBoost predicts P(user completes next week | last week, move) for each legal move, using
     swaps and equipment skips as features, and picks the hardest move it is confident about.
   - With no model, the swap-aware rule is used unchanged.

    python adaptive_week_two.py                      # simulate users, train, compare policies, save model
    python adaptive_week_two.py swap-demo            # sample user: same-day swaps -> next week's plan
    python adaptive_week_two.py swap <user_id> --without barbell            # preview today's swaps
    python adaptive_week_two.py swap <user_id> --location home --equipment dumbbell,bands --save

Swap options: --day N, --location home|gym|outdoors|mixed, --equipment a,b|none, --without a,b,
--exercise "Name" (repeatable), --rest-of-week, --save.

The simulation and swap-demo need no Supabase. The swap and demo parts use weekly_plan.py and
Fitsense-Issue-5.py (same folder). The training data is SIMULATED, so the comparison shows the
pipeline works, not that it helps real people.

Optional Supabase columns that let real logs carry swap information (run once in the SQL Editor):
    alter table workout_logs add column if not exists skip_reason text;   -- e.g. 'no_equipment'
    alter table workout_logs add column if not exists swapped boolean default false;
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "adaptive_week_two.json"

# ---------- Fixed rules (mirror weekly_plan.py) ----------
PROGRESS_RATE = 0.9
REPEAT_RATE = 0.6
ACTIONS = ["progress", "same dose", "reduce"]      # hardest -> easiest
LOAD_STEP = {"progress": 0.15, "same dose": 0.0, "reduce": -0.15}   # change in dose position (0-1)
TARGET_COMPLETION = 0.8     # a week "succeeds" if the user completes at least this share
MIN_CONFIDENCE = 0.70       # the model must be this sure before it chooses the harder move
LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2}
STATUS_SCORE = {"completed": 1.0, "partial": 0.5, "skipped": 0.0}
EQUIPMENT_REASONS = {"no_equipment", "location"}   # skip reasons that aren't about the user's capacity


def counted_statuses(state, swap_aware=True):
    """Day statuses the rules judge the week by. Equipment skips are left out when swap-aware."""
    excluded = state.get("equipment_skips", set()) if swap_aware else set()
    return [s for day, s in enumerate(state["statuses"], start=1) if day not in excluded]


def completion_rate(statuses):
    return sum(STATUS_SCORE[s] for s in statuses) / len(statuses) if statuses else 1.0


def rule_action(state, swap_aware=True):
    """weekly_plan.adaptation()'s rule; swap_aware=False is the original, which counts every skip."""
    statuses = counted_statuses(state, swap_aware)
    if not statuses:
        return "same dose"          # every day was blocked by equipment: no evidence either way
    rate = completion_rate(statuses)
    if rate >= PROGRESS_RATE and "skipped" not in statuses:
        return "progress"
    if rate >= REPEAT_RATE:
        return "same dose"
    return "reduce"


def days_for(action, state, swap_aware=True):
    """Days next week for a move (weekly_plan.adaptation()'s arithmetic)."""
    freq, previous = state["workout_frequency"], state["days"]
    did = sum(1 for s in state["statuses"] if s != "skipped")
    if swap_aware:
        did += len(state.get("equipment_skips", set()))   # they would have trained
    if action == "progress":
        return min(freq, previous + 1)
    if action == "same dose":
        return min(freq, previous)
    return max(1, min(freq, did + 1))


def load_for(action, state):
    """Average dose position (0 = bottom of guideline range, 1 = top) after the move."""
    return float(np.clip(state["load"] + LOAD_STEP[action], 0.0, 1.0))


def legal_actions(state):
    """The swap-aware rule's choice and its immediate neighbors: the model can nudge, never leap."""
    i = ACTIONS.index(rule_action(state))
    return ACTIONS[max(0, i - 1): i + 2]


# ---------- Features ----------
FEATURE_NAMES = ["age", "level", "workout_frequency", "days_last_week", "completed", "partial",
                 "skipped", "equipment_skips", "swapped_days", "rate", "swap_aware_rate", "load",
                 "days_next", "load_next", "days_change", "load_change", "action_index"]


def features(state, action):
    statuses = state["statuses"]
    days_next, load_next = days_for(action, state), load_for(action, state)
    equipment = len(state.get("equipment_skips", set()))
    return [float(state["age"]), float(LEVELS.get(state["fitness_level"], 0)), float(state["workout_frequency"]),
            float(state["days"]), statuses.count("completed"), statuses.count("partial"),
            statuses.count("skipped") - equipment, float(equipment), float(len(state.get("swapped", set()))),
            completion_rate(statuses), completion_rate(counted_statuses(state)), state["load"],
            float(days_next), load_next, float(days_next - state["days"]), load_next - state["load"],
            float(ACTIONS.index(action))]


# ---------- Model ----------
PARAMS = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 3, "eta": 0.05,
          "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 10, "lambda": 5.0, "seed": 0}


def _matrix(rows):
    import xgboost as xgb

    X = np.array([features(state, action) for state, action, _ in rows], dtype=float)
    y = np.array([done for _, _, done in rows], dtype=float)
    return xgb.DMatrix(X, label=y, feature_names=FEATURE_NAMES)


def train(train_rows, validation_rows):
    """rows are (state, action_taken, next_week_succeeded 0/1)."""
    import xgboost as xgb

    return xgb.train(PARAMS, _matrix(train_rows), num_boost_round=400,
                     evals=[(_matrix(validation_rows), "validation")],
                     early_stopping_rounds=30, verbose_eval=False)


def save_model(model, path=MODEL_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))


def load_model(path=MODEL_PATH):
    if not path.exists():
        return None
    import xgboost as xgb

    return xgb.Booster(model_file=str(path))


def success_probabilities(model, state, actions):
    import xgboost as xgb

    X = np.array([features(state, a) for a in actions], dtype=float)
    return dict(zip(actions, model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES)).tolist()))


def choose_adaptation(state, model=None, swap_aware=True):
    """Drop-in for weekly_plan.adaptation(): (action, days next week)."""
    rule = rule_action(state, swap_aware)
    if model is None or not swap_aware:
        return rule, days_for(rule, state, swap_aware)   # no model yet: the rule alone
    options = legal_actions(state)
    chance = success_probabilities(model, state, options)
    for action in options:                               # hardest first
        if chance[action] >= MIN_CONFIDENCE:
            return action, days_for(action, state)
    best = max(options, key=chance.get)                  # none clears the bar: the likeliest to succeed
    return best, days_for(best, state)


def decide(state, model=None):
    """The decision plus how it was made, for weekly_plan.next_week() and for display."""
    decision, days = choose_adaptation(state, model)
    return {"decision": decision, "days": days, "rule": rule_action(state),
            "original_rule": rule_action(state, swap_aware=False),
            "source": "xgboost" if model is not None else "rules",
            "probabilities": ({a: round(p, 3) for a, p in success_probabilities(model, state, legal_actions(state)).items()}
                              if model is not None else None),
            "completion": round(completion_rate(counted_statuses(state)), 3),
            "equipment_skips": sorted(state.get("equipment_skips", set())),
            "swapped": sorted(state.get("swapped", set()))}


# ---------- Simulated users (stand-in for real logs) ----------
SWAP_USE = 0.7   # share of equipment problems the user fixes with a same-day swap instead of skipping


def new_user(rng):
    return {"age": int(rng.integers(18, 65)), "fitness_level": str(rng.choice(list(LEVELS), p=[.5, .35, .15])),
            "workout_frequency": int(rng.integers(3, 6)),
            "capacity": float(rng.beta(2.5, 2.5)),       # hidden: how much dose they can sustain
            "motivation": float(rng.beta(4, 2)),         # hidden: how consistently they show up
            "disruption": float(rng.beta(1.5, 8))}       # hidden: how often equipment/location fails them


def simulate_week(user, days, load, rng, swaps=True):
    """(statuses, equipment_skips, swapped) for one week.

    Harder dose and more days than the user's capacity mean more skips. On a disrupted day the
    user either swaps (then trains as usual, slightly less likely to finish) or skips for an
    equipment reason, which has nothing to do with their capacity.
    """
    comfort_days = 2 + 3 * user["capacity"]
    logit = (6 * (user["capacity"] - load) + 2 * (user["motivation"] - 0.5)
             - 0.6 * max(0.0, days - comfort_days) + 1.0)
    p_done = 1 / (1 + np.exp(-logit))
    statuses, equipment_skips, swapped = [], set(), set()
    for day in range(1, days + 1):
        p = p_done
        if rng.random() < user["disruption"]:
            if not (swaps and rng.random() < SWAP_USE):
                statuses.append("skipped")
                equipment_skips.add(day)
                continue
            swapped.add(day)
            p *= 0.95
        u = rng.random()
        statuses.append("completed" if u < p else "partial" if u < p + (1 - p) * 0.35 else "skipped")
    return statuses, equipment_skips, swapped


def state_of(user, days, week, load):
    statuses, equipment_skips, swapped = week
    return {"age": user["age"], "fitness_level": user["fitness_level"],
            "workout_frequency": user["workout_frequency"], "days": days, "statuses": statuses,
            "equipment_skips": equipment_skips, "swapped": swapped, "load": load}


def training_rows(n_users, rng, weeks=6):
    """(user_id, [(state, action, succeeded)]). Actions are RANDOM so every move gets tried.

    Real logs only contain the move the rules chose, so a model trained on them could not learn what
    would have happened under the other moves. Exploration is what makes this learnable.
    """
    out = []
    for uid in range(n_users):
        user = new_user(rng)
        days, load = user["workout_frequency"], 0.0
        week = simulate_week(user, days, load, rng)
        rows = []
        for _ in range(weeks - 1):
            state = state_of(user, days, week, load)
            action = str(rng.choice(legal_actions(state)))
            days, load = days_for(action, state), load_for(action, state)
            week = simulate_week(user, days, load, rng)
            rows.append((state, action, int(completion_rate(counted_statuses(state_of(user, days, week, load)))
                                            >= TARGET_COMPLETION)))
        out.append((uid, rows))
    return out


def split_by_user(grouped, validation_share=0.2):
    cut = int(len(grouped) * (1 - validation_share))
    flat = lambda groups: [row for _, rows in groups for row in rows]
    return flat(grouped[:cut]), flat(grouped[cut:])


def run_policy(model, n_users, seed, swap_aware=True, weeks=8):
    """(completion on counted days, average dose position, average days planned) for one policy."""
    rng = np.random.default_rng(seed)
    rates, loads, planned = [], [], []
    for _ in range(n_users):
        user = new_user(rng)
        days, load = user["workout_frequency"], 0.0
        week = simulate_week(user, days, load, rng)
        for _ in range(weeks - 1):
            state = state_of(user, days, week, load)
            action, days = choose_adaptation(state, model, swap_aware)
            load = load_for(action, state)
            week = simulate_week(user, days, load, rng)
            rates.append(completion_rate(counted_statuses(state_of(user, days, week, load))))
            loads.append(load)
            planned.append(days)
    return float(np.mean(rates)), float(np.mean(loads)), float(np.mean(planned))


def simulate_and_train(n_users=1500, seed=0):
    grouped = training_rows(n_users, np.random.default_rng(seed))
    train_rows, validation_rows = split_by_user(grouped)
    return train(train_rows, validation_rows), len(train_rows), len(validation_rows)


def main_simulate():
    model, n_train, n_val = simulate_and_train()
    print(f"{n_train} training rows, {n_val} validation rows (simulated, with equipment disruptions).")
    save_model(model)
    print(f"Saved {MODEL_PATH}")

    # Same seed = same simulated people for every policy (a fair comparison).
    print("\nFresh simulated users, 8 weeks each (completion leaves out equipment-blocked days):")
    for label, m, aware in [("original rules (equipment skips = missed)", None, False),
                            ("swap-aware rules", None, True),
                            ("swap-aware rules + XGBoost", model, True)]:
        rate, load, days = run_policy(m, 500, seed=123, swap_aware=aware)
        print(f"  {label:<42}: completion {rate:.1%}, dose position {load:.2f}, days planned {days:.2f}")

    example = {"age": 34, "fitness_level": "beginner", "workout_frequency": 4, "days": 4,
               "statuses": ["completed", "completed", "skipped", "completed"],
               "equipment_skips": {3}, "swapped": {2}, "load": 0.2}
    print("\nExample: day 2 swapped and completed, day 3 skipped (gym closed), days 1 and 4 completed")
    print("  original rule  :", rule_action(example, swap_aware=False))
    print("  swap-aware rule:", rule_action(example))
    print("  P(next week succeeds):",
          {a: round(p, 2) for a, p in success_probabilities(model, example, legal_actions(example)).items()})
    print("  final decision :", choose_adaptation(example, model))


# ---------- Same-day swaps (real plans; uses weekly_plan.py) ----------
LOCATIONS = ("home", "gym", "outdoors", "mixed")


def _planning():
    import exercise_ranker
    import weekly_plan

    return weekly_plan, weekly_plan.recommender, exercise_ranker


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
    _, recommender, _ = _planning()
    groups = recommender.recommend_exercises(todays_profile(profile, today), exercises, None, per_group=None)
    without = {item.lower() for item in today.get("without") or []}
    return {group: [e for e in matches if (e["equipment"] or "").lower() not in without]
            for group, matches in groups.items()}


def similarity(original, candidate, in_week=frozenset()):
    """Sort key: higher is closer to the original exercise (and fresher for this week)."""
    _, recommender, _ = _planning()
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
    _, _, exercise_ranker = _planning()
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
    if equipment.lower() in {w.lower() for w in today.get("without") or []}:
        return f"no {equipment} today"
    where = {"outdoors": "outdoors", "home": "at home"}.get(today_profile["workout_location"],
                                                              f"at the {today_profile['workout_location']}")
    label = "special equipment" if equipment == "other" else equipment
    return f"needs {label}, not available {where} today"


def swap_days(profile, plan, days, today, exercises, force_names=(), ranker=None):
    """(new plan, swaps). Replaces items on the given days that today's conditions rule out.

    Each swap is {"day", "group", "old", "new", "new_item", "old_dose", "new_dose", "reason"};
    "new" is None when no allowed alternative exists (the item is left as it was and flagged).
    """
    weekly_plan, recommender, _ = _planning()
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
        reason = "user asked to swap it" if forced else unavailable_reason(exercise, today_profile, today)
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


def format_swaps(swaps):
    if not swaps:
        return "No swaps needed: everything on that day can still be done."
    lines = []
    for s in swaps:
        if s["new"] is None:
            lines.append(f"Day {s['day']} [{s['group']}] {s['old']['name']} ({s['old_dose']}): kept, {s['reason']}")
        else:
            lines.append(f"Day {s['day']} [{s['group']}] {s['old']['name']} ({s['old_dose']})  ->  "
                         f"{s['new']['name']} ({s['new']['equipment'] or 'no equipment'}, {s['new_dose']})   "
                         f"[{s['reason']}]")
    return "\n".join(lines)


def save_swaps(client, plan_id, swaps, exercises):
    """Update the swapped rows of plan_exercises in place. Returns how many rows changed."""
    weekly_plan, _, _ = _planning()
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
            print(f"  ! Could not find {swap['old']['name']} on day {swap['day']} in Supabase; skipped.")
            continue
        item = swap["new_item"]
        (client.table("plan_exercises")
         .update({"exercise_id": ids[swap["new"]["name"].strip().lower()], "sets": item["sets"],
                  "reps": item["reps"], "duration_minutes": item["minutes"]})
         .eq("plan_exercise_id", row["plan_exercise_id"]).execute())
        rows.remove(row)
        changed += 1
    return changed


# ---------- Bridge: real plans and logs -> adaptation state -> next week's plan ----------

def dose_position(profile, plan):
    """Average position of the plan's doses in their guideline ranges (0 = bottom, 1 = top)."""
    _, recommender, _ = _planning()
    positions = []
    for item in plan["items"]:
        bounds = recommender.dose_range(profile, item["exercise"], plan["days"])
        for key in ("reps", "minutes", "sets"):
            low_high = bounds[key]
            if low_high and low_high[1] > low_high[0] and item.get(key) is not None:
                positions.append((item[key] - low_high[0]) / (low_high[1] - low_high[0]))
                break
    return float(np.mean(positions)) if positions else 0.0


def state_from_plan(profile, plan, logs):
    """Adaptation state from a saved plan and its linked logs.

    Logs may carry skip_reason ('no_equipment' / 'location') and swapped (true) once the
    optional workout_logs columns exist; without them every skip counts, as in weekly_plan.py.
    """
    weekly_plan, _, _ = _planning()
    statuses = weekly_plan.day_statuses(plan, logs)
    equipment = {log["day_number"] for log in logs
                 if log.get("skip_reason") in EQUIPMENT_REASONS and statuses.get(log.get("day_number")) == "skipped"}
    swapped = {log["day_number"] for log in logs if log.get("swapped") and log.get("day_number") in statuses}
    return {"age": profile["age"], "fitness_level": profile["fitness_level"],
            "workout_frequency": profile["workout_frequency"], "days": plan["days"],
            "statuses": [statuses[d] for d in range(1, plan["days"] + 1)],
            "equipment_skips": equipment, "swapped": swapped, "load": dose_position(profile, plan)}


def next_week_plan(profile, exercises, previous, logs, model=None, ranker=None):
    """(plan, (decision, days)): weekly_plan.next_week with this file's decision.

    weekly_plan.next_week calls decide() itself; days skipped only because of equipment keep
    their exercises and follow the week's overall decision.
    """
    weekly_plan, _, _ = _planning()
    plan = weekly_plan.next_week(profile, exercises, previous, logs, ranker, model)
    return plan, (plan["adaptation"]["decision"], plan["adaptation"]["days"])


# ---------- Commands ----------
DEMO_USER = {"user_id": "sample-user", "name": "Sam Sample", "age": 29, "points": 0,
             "fitness_level": "intermediate", "fitness_goal": "build_muscle", "workout_location": "gym",
             "workout_frequency": 4, "equipment": [], "workout_preferences": ["strength"]}


def main_swap_demo():
    from datetime import date

    weekly_plan, recommender, exercise_ranker = _planning()
    exercises = recommender.load_exercises()
    ranker = exercise_ranker.load_model()
    model = load_model()
    if model is None:
        print("No saved adaptation model: training one on simulated users first...")
        model, *_ = simulate_and_train()
        save_model(model)
    profile = dict(DEMO_USER)
    plan = weekly_plan.first_week(profile, exercises, date(2026, 11, 2), ranker)
    for item in plan["items"]:        # pretend a few good weeks have passed, so there is progress to keep
        if item["reps"]:
            item["reps"] = 10
    print(weekly_plan.format_plan(profile, plan))

    print("\n===== Tuesday (day 2): at the gym, but no barbell today =====")
    plan, swaps = swap_days(profile, plan, {2}, {"without": ["barbell"]}, exercises, ranker=ranker)
    print(format_swaps(swaps))
    print("\n===== Wednesday (day 3): training outdoors today =====")
    _, swaps = swap_days(profile, plan, {3}, {"location": "outdoors"}, exercises, ranker=ranker)
    print(format_swaps(swaps))
    print("(The user decides to skip instead and logs the reason: no equipment.)")

    logs = [{"day_number": 1, "completion_status": "completed"},
            {"day_number": 2, "completion_status": "completed", "swapped": True},
            {"day_number": 3, "completion_status": "skipped", "skip_reason": "no_equipment"},
            {"day_number": 4, "completion_status": "completed"}]
    state = state_from_plan(profile, plan, logs)
    print("\n===== End of the week =====")
    print("Logged: day 1 completed, day 2 completed (swapped), day 3 skipped (no equipment), day 4 completed")
    original = rule_action(state, swap_aware=False)
    print(f"  original rule                 : ('{original}', {days_for(original, state, swap_aware=False)})"
          "  <- counts the equipment skip as a missed workout")
    print(f"  swap-aware rule               : {choose_adaptation(state, None)}")
    print("  XGBoost P(next week succeeds) :",
          {a: round(p, 2) for a, p in success_probabilities(model, state, legal_actions(state)).items()})
    next_plan, decision = next_week_plan(profile, exercises, plan, logs, model, ranker)
    print(f"  final decision                : {decision}")
    print("\nNext week's plan:")
    print(weekly_plan.format_plan(profile, next_plan))


def parse_swap(argv):
    options = {"day": None, "today": {}, "exercise": [], "rest_of_week": False, "save": False}
    user_id, i = None, 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--save", "--rest-of-week"):
            options[arg[2:].replace("-", "_")] = True
            i += 1
            continue
        if arg.startswith("--"):
            if i + 1 >= len(argv):
                raise ValueError(f"{arg} needs a value.")
            value = argv[i + 1]
            if arg == "--day":
                options["day"] = int(value)
            elif arg == "--location":
                if value not in LOCATIONS:
                    raise ValueError(f"--location must be one of {', '.join(LOCATIONS)}.")
                options["today"]["location"] = value
            elif arg == "--equipment":
                options["today"]["equipment"] = [] if value == "none" else [v.strip().lower() for v in value.split(",") if v.strip()]
            elif arg == "--without":
                options["today"]["without"] = [v.strip().lower() for v in value.split(",") if v.strip()]
            elif arg == "--exercise":
                options["exercise"].append(value)
            else:
                raise ValueError(f"Unknown option {arg}.")
            i += 2
            continue
        if user_id is not None:
            raise ValueError(f"Unexpected argument {arg!r}. Put exercise names in quotes.")
        user_id = arg
        i += 1
    if not user_id:
        raise ValueError("Give a user_id.")
    if not options["today"] and not options["exercise"]:
        raise ValueError("Say what changed today: --without, --location/--equipment, or --exercise.")
    return user_id, options


def main_swap(argv):
    weekly_plan, recommender, exercise_ranker = _planning()
    from progress_forecast import week_start

    try:
        user_id, options = parse_swap(argv)
    except ValueError as error:
        print(error)
        print(__doc__)
        return
    client = recommender.supabase_client()
    try:
        profile = recommender.load_profile_from_supabase(user_id)
    except LookupError as error:
        print(error)
        return
    exercises = recommender.load_exercises()
    ranker = exercise_ranker.load_model()
    start = week_start(datetime.now(timezone.utc).date())

    saved = weekly_plan.load_plans(client, exercises, user_id).get(user_id, [])
    current = next(((plan_id, plan) for plan_id, plan in saved if plan["week_start"] == start), None)
    if current is None:
        print(f"{profile['name']} has no plan for the week of {start} yet. Run: python Fitsense-Issue-5.py --user {user_id}")
        return
    plan_id, plan = current
    logs = client.table("workout_logs").select("*").eq("plan_id", plan_id).execute().data
    logged = {log.get("day_number") for log in logs}
    day = options["day"] or next((d for d in range(1, plan["days"] + 1) if d not in logged), plan["days"])
    if not 1 <= day <= plan["days"]:
        print(f"This week's plan has {plan['days']} days; --day {day} is out of range.")
        return
    days = set(range(day, plan["days"] + 1)) if options["rest_of_week"] else {day}

    new_plan, swaps = swap_days(profile, plan, days, options["today"], exercises, options["exercise"], ranker)
    which = f"days {min(days)}-{max(days)}" if len(days) > 1 else f"day {day}"
    print(f"{profile['name']}: week of {start}, {which} of {plan['days']}")
    print("\n" + format_swaps(swaps))
    print("\n--- Updated plan ---")
    for d in sorted(days):
        print(f"Day {d}:")
        for item in new_plan["items"]:
            if item["day"] == d:
                print(f"  - [{item['group']}] {item['exercise']['name']} "
                      f"({item['exercise']['equipment'] or 'no equipment'}): {weekly_plan.dose_text(profile, item)}")
    if options["save"]:
        print(f"\nSaved: {save_swaps(client, plan_id, swaps, exercises)} exercise(s) updated in this week's plan.")
        print("When the user logs these days, save swapped = true on the log (and skip_reason "
              "'no_equipment' if they skip instead), so next week's adaptation doesn't count it as missed.")
    elif any(s["new"] for s in swaps):
        print("\nPreview only. Add --save to update this week's plan in Supabase.")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "simulate"
    if command == "simulate":
        main_simulate()
    elif command == "swap-demo":
        main_swap_demo()
    elif command == "swap":
        main_swap(sys.argv[2:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

# ---------- How weekly_plan.py uses this file ----------
# weekly_plan.next_week() calls state_from_plan() and decide() for every new week's plan;
# weekly_plan.run_weekly() and current_plan() load models/adaptive_week_two.json if it exists.
# Without that file the swap-aware rule decides, which equals the old rule when no log has a
# skip_reason. `python weekly_plan.py swap ...` runs main_swap() from here.
#
# ---------- What real data needs ----------
# 1. Logs linked to plans (plan_id + day_number), plus swapped / skip_reason on each log.
# 2. Exploration: occasionally (10-20% of users) apply the rule's neighboring move, so the logs show
#    outcomes for moves the rules wouldn't pick. Without it the model can only copy the rules.
# 3. Label = the user's completion the following week; split by user and time; compare against the
#    swap-aware rules on held-out users before enabling.