"""XGBoost model that decides how each week's plan adapts: step up, keep the dose, or ease off.

weekly_plan.change_options() lists the changes next week may make (progress / same dose /
reduce, each with its number of days). For each one this model predicts the share of next
week's plan the user will complete, from how the last weeks went, the profile, and the change
itself. The plan takes the most demanding change predicted to reach TARGET_COMPLETION, or the
best-predicted one when none does. Without a model file, weekly_plan.rule_change() decides.

Training rows are (week before, change made, completion of the week after):
- Supabase: consecutive saved plans with their workout_logs, once the later week is over
- simulated users (bootstrap only, not real data) whose changes are picked at random, so every
  change is seen after every kind of week

    python adaptation_model.py train               # simulated users, saves MODEL_PATH
    python adaptation_model.py train --supabase    # simulated rows plus real plans and logs (REAL_WEIGHT)
    python adaptation_model.py evaluate            # held-out error, and rules vs model on simulated users
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "adaptation.json"
# Supabase weeks are few (most users have one finished week), so they're added to the simulated
# rows rather than replacing them; each counts this many times. Picked by cross-validation on real users.
REAL_WEIGHT = 5
# Aim for a plan the user is expected to finish most of; below this the change is too much.
TARGET_COMPLETION = 0.75
# Most demanding first; also the order choose() tries them in.
CHANGES = {"progress": 1, "same dose": 0, "reduce": -1}
# Simulated dose steps above the bottom of the guideline range (sets/reps/minutes go up in steps).
MAX_STEPS = 6

LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 2}
GOALS = ["build_muscle", "lose_weight", "improve_endurance", "general_fitness", "increase_flexibility"]

FEATURE_NAMES = (
    ["last_rate", "last_skipped", "last_partial", "last_days", "earlier_rate", "mean_rate", "weeks",
     "frequency", "age", "user_level", "change", "next_days", "days_delta"]
    + [f"goal={g}" for g in GOALS]
)

PARAMS = {"objective": "reg:logistic", "eval_metric": "mae", "max_depth": 4, "eta": 0.05,
          "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 10, "lambda": 5.0, "seed": 0}


def week_summary(statuses):
    """How a week went, from each plan day's completion_status (unlogged days are "skipped")."""
    statuses = list(statuses)
    days = len(statuses) or 1
    done = sum(1.0 if s == "completed" else 0.5 if s == "partial" else 0.0 for s in statuses)
    return {"rate": done / days, "skipped": statuses.count("skipped") / days,
            "partial": statuses.count("partial") / days, "days": len(statuses)}


def feature_row(profile, last, earlier_rates, change, next_days):
    """One row for (the week just planned, the change for next week). earlier_rates: weeks before last, oldest first."""
    rates = list(earlier_rates) + [last["rate"]]
    age = profile.get("age")
    return (
        [last["rate"], last["skipped"], last["partial"], float(last["days"]),
         earlier_rates[-1] if earlier_rates else float("nan"), float(np.mean(rates[-4:])), float(len(rates)),
         float(profile.get("workout_frequency") or 0), float(age) if age is not None else float("nan"),
         float(LEVELS.get(profile.get("fitness_level"), 0)), float(CHANGES[change]), float(next_days),
         float(next_days - last["days"])]
        + [1.0 if profile.get("fitness_goal") == g else 0.0 for g in GOALS]
    )


def predict(model, profile, last, earlier_rates, options):
    """{change: predicted completion of next week} for each of options ({change: days})."""
    import xgboost as xgb

    changes = list(options)
    X = np.array([feature_row(profile, last, earlier_rates, c, options[c]) for c in changes], dtype=float)
    return dict(zip(changes, model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES)).tolist()))


def choose(predicted):
    """The most demanding change expected to reach TARGET_COMPLETION, else the best-predicted one."""
    for change in CHANGES:
        if predicted.get(change, -1.0) >= TARGET_COMPLETION:
            return change
    return max(predicted, key=predicted.get)


def model_policy(model):
    def policy(profile, last, earlier_rates, statuses, options):
        return choose(predict(model, profile, last, earlier_rates, options))
    return policy


def rule_policy(profile, last, earlier_rates, statuses, options):
    import weekly_plan

    return weekly_plan.rule_change(statuses)


def random_policy(rng):
    def policy(profile, last, earlier_rates, statuses, options):
        return str(rng.choice(list(options)))
    return policy


# ---------- Simulated users ----------

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def simulate_user(rng, weeks, policy, user_id):
    """One user's weeks under policy. Returns (training rows, completion rates, dose steps reached).

    Assumptions (not measured): each user has a fitness that grows with the training they finish,
    a motivation that rises after good weeks and drops after weeks that were too much, and a
    number of days a week life usually allows. A dose above their fitness makes days harder to
    finish, and more planned days than they have time for get skipped.
    """
    import weekly_plan

    level = str(rng.choice(["beginner", "intermediate", "advanced"], p=[0.5, 0.35, 0.15]))
    profile = {"user_id": user_id, "age": int(rng.integers(18, 65)), "fitness_level": level,
               "fitness_goal": str(rng.choice(GOALS)), "workout_frequency": int(rng.integers(2, 7))}
    fitness = float(rng.normal(LEVELS[level] * 0.5, 0.8))
    motivation = float(rng.beta(6, 2))
    free_days = float(np.clip(rng.normal(profile["workout_frequency"] * 0.85, 1.0), 1.0, 7.0))
    days, steps = weekly_plan.training_days(profile), 0
    rates, rows, pending = [], [], None
    for _ in range(weeks):
        available = int(np.clip(round(rng.normal(free_days, 0.8)), 0, 7))
        strain = steps - fitness
        p_done = motivation * float(_sigmoid(2.0 - 1.5 * strain))
        statuses = {}
        for day in range(1, days + 1):
            u = rng.random()
            statuses[day] = ("skipped" if day > available else "completed" if u < p_done
                             else "partial" if u < p_done + 0.4 * (1 - p_done) else "skipped")
        last = week_summary(statuses.values())
        if pending:
            rows.append((pending, last["rate"]))
        fitness += 0.35 * last["rate"] - 0.05
        motivation += 0.04 if last["rate"] >= 0.8 else -0.06 if last["rate"] < 0.5 else 0.0
        motivation = float(np.clip(motivation - (0.08 if strain > 1.0 else 0.0) + rng.normal(0, 0.03), 0.1, 1.0))

        options = weekly_plan.change_options(profile, days, statuses)
        change = policy(profile, last, rates, statuses, options)
        pending = feature_row(profile, last, rates, change, options[change])
        rates.append(last["rate"])
        steps = int(np.clip(steps + CHANGES[change], 0, MAX_STEPS))
        days = options[change]
    return rows, rates, steps


def synthetic_rows(n_users=400, seed=0):
    """[(user_id, [(features, completion)])] from simulated users whose changes are random."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_users):
        rows, _, _ = simulate_user(rng, int(rng.integers(6, 21)), random_policy(rng), f"sim-{i}")
        out.append((f"sim-{i}", rows))
    return out


def compare_policies(model, n_users=300, weeks=12, seed=1):
    """Mean completion and dose steps reached by the same simulated users under each policy."""
    report = {}
    for name, policy in (("rules", rule_policy), ("model", model_policy(model))):
        rng = np.random.default_rng(seed)   # same users and luck for both
        done, steps = [], []
        for i in range(n_users):
            _, rates, reached = simulate_user(rng, weeks, policy, f"cmp-{i}")
            done.append(np.mean(rates))
            steps.append(reached)
        report[name] = (float(np.mean(done)), float(np.mean(steps)))
    return report


# ---------- Supabase ----------

def _volume(item):
    return item["minutes"] if item.get("minutes") is not None else (item.get("sets") or 0) * (item.get("reps") or 1)


def change_made(previous, plan):
    """Which change turned previous into plan: the dose direction, else the change in days."""
    before = {i["exercise"]["id"]: _volume(i) for i in previous["items"]}
    shared = [(before[i["exercise"]["id"]], _volume(i)) for i in plan["items"] if i["exercise"]["id"] in before]
    direction = np.sign(sum(np.sign(after - was) for was, after in shared)) if shared else 0
    if direction == 0:
        direction = np.sign(plan["days"] - previous["days"])
    return {1: "progress", 0: "same dose", -1: "reduce"}[int(direction)]


def training_rows_from_supabase(client, today=None):
    """[(user_id, rows)] from each user's consecutive saved plans whose later week is over."""
    import weekly_plan

    today = today or datetime.now(timezone.utc).date()
    exercises = weekly_plan.recommender.load_exercises()
    profiles = {row["user_id"]: weekly_plan.recommender.profile_from_supabase_row(row)
                for row in weekly_plan.fetch_all(client, "profiles", "*, user_preferences(available_equipment), "
                                                 "user_gamification(total_xp)", "user_id")}
    user_logs = {}
    for log in weekly_plan.fetch_all(client, "workout_logs", "workout_log_id, user_id, plan_id, day_number, "
                                     "workout_date, completion_status", "workout_log_id"):
        user_logs.setdefault(log["user_id"], []).append(log)
    out = []
    for user_id, saved in weekly_plan.load_plans(client, exercises).items():
        profile = profiles.get(user_id)
        if not profile:
            continue
        logs = {}   # by plan_id, with logs from each plan's week linked to it the way the app does
        for log in weekly_plan.link_logs(saved, user_logs.get(user_id, [])):
            logs.setdefault(log.get("plan_id"), []).append(log)
        rates, rows = [], []
        for (prev_id, previous), (plan_id, plan) in zip(saved, saved[1:]):
            prev_statuses = weekly_plan.day_statuses(previous, logs.get(prev_id, []))
            last = week_summary(prev_statuses.values())
            if plan["week_start"] + timedelta(days=7) <= today:
                rows.append((feature_row(profile, last, rates, change_made(previous, plan), plan["days"]),
                             weekly_plan.completion_rate(plan, logs.get(plan_id, []))))
            rates.append(last["rate"])
        if rows:
            out.append((user_id, rows))
    return out


# ---------- Training ----------

def split_by_user(grouped, validation_share=0.2):
    cut = max(1, int(len(grouped) * (1 - validation_share)))
    flat = lambda groups: [row for _, rows in groups for row in rows]
    return flat(grouped[:cut]), flat(grouped[cut:])


def weighted(rows, weight):
    return [(features, completion, weight) for features, completion, *_ in rows]


def _matrix(rows):
    """Rows are (features, completion) or (features, completion, weight)."""
    import xgboost as xgb

    X = np.array([r[0] for r in rows], dtype=float)
    y = np.array([r[1] for r in rows], dtype=float)
    w = np.array([r[2] if len(r) > 2 else 1.0 for r in rows], dtype=float)
    return xgb.DMatrix(X, label=y, weight=w, feature_names=FEATURE_NAMES)


def train(train_rows, validation_rows=None):
    import xgboost as xgb

    if len({r[0][FEATURE_NAMES.index("change")] for r in train_rows}) < 2:
        raise ValueError("Training data needs weeks after more than one kind of change.")
    dtrain = _matrix(train_rows)
    if validation_rows:
        return xgb.train(PARAMS, dtrain, num_boost_round=500, evals=[(_matrix(validation_rows), "validation")],
                         early_stopping_rounds=30, verbose_eval=False)
    return xgb.train(PARAMS, dtrain, num_boost_round=200)


def save_model(model, path=MODEL_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))


def load_model(path=MODEL_PATH):
    """The saved model, or None (no file, or XGBoost not installed): plans then use the rules."""
    if not path.exists():
        return None
    try:
        import xgboost as xgb
    except ImportError:
        return None
    return xgb.Booster(model_file=str(path))


def evaluate(model, rows):
    """(mean error of "same as last week", mean error of the model) on held-out rows."""
    import xgboost as xgb

    X = np.array([r[0] for r in rows], dtype=float)
    y = np.array([r[1] for r in rows], dtype=float)
    predicted = model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES))
    return float(np.mean(np.abs(X[:, 0] - y))), float(np.mean(np.abs(predicted - y)))


def train_with_supabase(client):
    """Simulated rows plus Supabase rows weighted REAL_WEIGHT; prints held-out error on real users."""
    real = training_rows_from_supabase(client)
    simulated = [row for _, rows in synthetic_rows() for row in rows]
    total = sum(len(rows) for _, rows in real)
    print(f"{total} Supabase rows from {len(real)} users (x{REAL_WEIGHT}), plus {len(simulated)} simulated rows.")
    if not real:
        raise ValueError("No finished weeks with a saved plan before them in Supabase.")
    shuffled = [real[i] for i in np.random.default_rng(0).permutation(len(real))]
    real_train, real_validation = split_by_user(shuffled)
    if real_validation:
        model = train(simulated + weighted(real_train, REAL_WEIGHT))
        average = float(np.mean([r[1] for r in real_train]))
        _, ml = evaluate(model, real_validation)
        guess = float(np.mean([abs(average - r[1]) for r in real_validation]))
        print(f"Held-out Supabase users, error in next week's completion: "
              f"guessing the average {guess:.3f}, XGBoost {ml:.3f}")
    return train(simulated + weighted([row for _, rows in real for row in rows], REAL_WEIGHT))


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("train", "evaluate"):
        print("Usage: python adaptation_model.py train [--supabase] | evaluate")
        return
    if command == "train" and "--supabase" in sys.argv:
        import weekly_plan

        save_model(train_with_supabase(weekly_plan.recommender.supabase_client()))
        print(f"Saved {MODEL_PATH}.")
        return
    grouped = synthetic_rows()
    total = sum(len(rows) for _, rows in grouped)
    print(f"{total} training rows from {len(grouped)} simulated users (bootstrap only, not real data).")
    train_rows, validation_rows = split_by_user(grouped)
    model = train(train_rows, validation_rows or None)
    if validation_rows:
        base, ml = evaluate(model, validation_rows)
        print(f"Held-out error in next week's completion: same-as-last-week {base:.3f}, XGBoost {ml:.3f}")
    if command == "evaluate":
        report = compare_policies(model)
        print("Simulated users, 12 weeks:   completion   dose steps reached")
        for name, (done, steps) in report.items():
            print(f"  {name:<6}                    {done:6.1%}   {steps:8.2f}")
    if command == "train":
        save_model(model)
        print(f"Saved {MODEL_PATH}.")


if __name__ == "__main__":
    main()
