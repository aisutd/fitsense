from datetime import date, timedelta
from pathlib import Path
import sys

import numpy as np

import progress_forecast as pf

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "weight_forecast.json"
MIN_TRAINING_ROWS = 300
MIN_WEEKS_FOR_MODEL = 2
MAX_CORRECTION_KG_PER_WEEK = 0.5

LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2}
GOALS = ["lose_weight", "build_muscle", "improve_endurance", "general_fitness", "increase_flexibility"]

FEATURE_NAMES = (
    ["horizon", "weeks_of_data", "weeks_since_signup", "baseline_level", "baseline_slope",
     "prior_slope", "adherence", "recent_slope", "volatility", "kg_from_start", "recent_workouts",
     "avg_steps", "age", "user_level", "workout_frequency"]
    + [f"goal={g}" for g in GOALS]
)


def _recent_slope(points, window=3):
    recent = points[-window:]
    if len(recent) < 2 or recent[-1][0] == recent[0][0]:
        return 0.0
    return (recent[-1][1] - recent[0][1]) / (recent[-1][0] - recent[0][0])


def _volatility(points):
    values = [y for _, y in points]
    return float(np.std(np.diff(values))) if len(values) >= 3 else 0.0


def _mean_of_last(history, n=4):
    values = [v for _, v in history[-n:]]
    return float(np.mean(values)) if values else float("nan")


def user_features(profile, result, origin):
    weight = result["weight_kg"]
    weekly = [(pf.week_index(monday, origin), value) for monday, value in weight["history"]]
    prior = pf.goal_weight_slope(profile, weight["level"]) * weight.get("adherence", 1.0)
    created = profile.get("created_at")
    since_signup = max(0, (origin - pf.week_start(pf.to_date(created))).days // 7) if created else 0
    steps = result.get("daily_steps")
    age = profile.get("age")
    return (
        [float(weight["weeks_of_data"]), float(since_signup), weight["level"], weight["slope"], prior,
         weight.get("adherence", 1.0), _recent_slope(weekly), _volatility(weekly),
         weekly[-1][1] - weekly[0][1] if weekly else 0.0,
         _mean_of_last(result["workouts_per_week"]["history"]),
         _mean_of_last(steps["history"]) if steps else float("nan"),
         float(age) if age is not None else float("nan"),
         float(LEVELS.get(profile.get("fitness_level"), 0)), float(profile.get("workout_frequency") or 0)]
        + [1.0 if profile.get("fitness_goal") == g else 0.0 for g in GOALS]
    )


def feature_row(shared, horizon):
    return [float(horizon)] + shared


def actual_weekly_weights(rows):
    weeks = {}
    for row in rows:
        if row.get("weight_kg") is not None and row.get("recorded_at"):
            weeks.setdefault(pf.week_start(pf.to_date(row["recorded_at"])), []).append(float(row["weight_kg"]))
    return {monday: sum(values) / len(values) for monday, values in weeks.items()}


def training_rows(profile, history, end_day):
    actual = actual_weekly_weights(history["body_measurements"])
    if not actual:
        return []
    rows = []
    today = pf.week_start(pf.to_date(profile["created_at"])) + timedelta(days=7)
    while today <= end_day:
        origin = pf.last_complete_week(today)
        result = pf.forecast_user(profile, history, today, weight_model=None, use_ml=False)
        weight = result.get("weight_kg")
        if weight and weight["weeks_of_data"] >= MIN_WEEKS_FOR_MODEL:
            shared = user_features(profile, result, origin)
            for h, (_, predicted) in zip(pf.HORIZONS, weight["predictions"]):
                target = actual.get(origin + timedelta(days=7 * h))
                if target is not None:
                    rows.append((feature_row(shared, h), target - predicted, predicted, target))
        today += timedelta(days=7)
    return rows


def training_rows_from_supabase(client):
    history = pf.load_history(client)
    today = date.today()
    out = []
    for profile in pf.fetch_all(client, "profiles", "*", "user_id"):
        user_history = history.get(profile["user_id"])
        if user_history:
            out.append((profile["user_id"], training_rows(profile, user_history, today)))
    return out


def synthetic_user(rng, end_monday, user_id):
    weeks = int(rng.integers(8, 31))
    start = end_monday - timedelta(days=7 * (weeks - 1))
    goal = str(rng.choice(["lose_weight", "build_muscle", "general_fitness"], p=[0.5, 0.3, 0.2]))
    level = str(rng.choice(list(LEVELS), p=[0.5, 0.35, 0.15]))
    age = int(rng.integers(18, 60))
    freq = int(rng.integers(2, 6))
    weight = float(np.clip(rng.normal(80, 14), 50, 140))
    response = float(np.clip(rng.normal(1.0, 0.25) + (35 - age) * 0.005, 0.3, 1.8))
    plateau_weeks = float(rng.uniform(5, 18))
    adherence = float(rng.beta(5, 2))
    dropout = 0.08 if level == "beginner" else 0.04

    profile = {"user_id": user_id, "created_at": start.isoformat() + "T08:00:00+00:00", "weight_kg": weight,
               "age": age, "fitness_goal": goal, "fitness_level": level, "workout_frequency": freq}
    history = {"body_measurements": [], "workout_logs": [], "activity_logs": []}
    true_weight = weight
    for k in range(weeks):
        monday = start + timedelta(days=7 * k)
        if rng.random() < dropout:
            adherence = float(rng.uniform(0.0, 0.3))
        adherence = float(np.clip(adherence + rng.normal(0.02 if adherence < 0.7 else 0, 0.08), 0.0, 1.0))
        done = int(rng.binomial(freq, adherence))
        for d in range(done):
            history["workout_logs"].append({"workout_date": (monday + timedelta(days=d)).isoformat(),
                                            "completion_status": "completed"})
        for d in rng.choice(7, size=3, replace=False):
            history["activity_logs"].append({"log_date": (monday + timedelta(days=int(d))).isoformat(),
                                             "steps": int(max(1500, rng.normal(5000 + 4500 * adherence, 900)))})
        for d in rng.choice(7, size=int(rng.integers(1, 4)), replace=False):
            reading = true_weight + rng.normal(0, 0.45)
            history["body_measurements"].append(
                {"recorded_at": (monday + timedelta(days=int(d))).isoformat() + "T07:00:00+00:00",
                 "weight_kg": round(float(reading), 2)})
        expected = pf.goal_weight_slope(profile, true_weight)
        true_weight += expected * (done / freq) * response * float(np.exp(-k / plateau_weeks))
        true_weight += rng.normal(0, 0.12)
    return profile, history


def synthetic_rows(n_users=300, seed=0, end_monday=None):
    rng = np.random.default_rng(seed)
    end_monday = end_monday or pf.week_start(date(2026, 10, 19))
    out = []
    for i in range(n_users):
        profile, history = synthetic_user(rng, end_monday, f"sim-{i}")
        out.append((profile["user_id"], training_rows(profile, history, end_monday + timedelta(days=7))))
    return out


PARAMS = {"objective": "reg:squarederror", "eval_metric": "mae", "max_depth": 3, "eta": 0.05,
          "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 10, "lambda": 5.0, "seed": 0}


def split_by_user(grouped, validation_share=0.2):
    cut = max(1, int(len(grouped) * (1 - validation_share)))
    flat = lambda groups: [row for _, rows in groups for row in rows]
    return flat(grouped[:cut]), flat(grouped[cut:])


def _matrix(rows):
    import xgboost as xgb

    X = np.array([r[0] for r in rows], dtype=float)
    y = np.array([r[1] for r in rows], dtype=float)
    return xgb.DMatrix(X, label=y, feature_names=FEATURE_NAMES)


def train(train_rows, validation_rows=None):
    import xgboost as xgb

    if len({r[1] > 0 for r in train_rows}) < 2:
        raise ValueError("Training data needs forecasts that were both too high and too low.")
    dtrain = _matrix(train_rows)
    if validation_rows:
        dval = _matrix(validation_rows)
        return xgb.train(PARAMS, dtrain, num_boost_round=400, evals=[(dval, "validation")],
                         early_stopping_rounds=30, verbose_eval=False)
    return xgb.train(PARAMS, dtrain, num_boost_round=150)


def save_model(model, path=MODEL_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))


def load_model(path=MODEL_PATH):
    if not path.exists():
        return None
    try:
        import xgboost as xgb
    except ImportError:
        return None
    return xgb.Booster(model_file=str(path))


def corrections(model, shared):
    import xgboost as xgb

    X = np.array([feature_row(shared, h) for h in pf.HORIZONS], dtype=float)
    raw = model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES))
    caps = [max(1.0, MAX_CORRECTION_KG_PER_WEEK * h) for h in pf.HORIZONS]
    return [float(np.clip(c, -cap, cap)) for c, cap in zip(raw, caps)]


def apply(model, profile, result, origin):
    weight = result.get("weight_kg")
    if model is None or not weight or weight["weeks_of_data"] < MIN_WEEKS_FOR_MODEL:
        return False
    fixes = corrections(model, user_features(profile, result, origin))
    weight["baseline_predictions"] = list(weight["predictions"])
    weight["ml_corrections"] = fixes
    weight["predictions"] = [(target, pf.clip("weight_kg", value + fix))
                             for (target, value), fix in zip(weight["predictions"], fixes)]
    weight["model_version"] = pf.ML_MODEL_VERSION
    return True


def evaluate(model, rows):
    import xgboost as xgb

    X = np.array([r[0] for r in rows], dtype=float)
    predicted = model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES))
    out = {}
    for h in pf.HORIZONS:
        picked = [i for i, r in enumerate(rows) if r[0][0] == h]
        if not picked:
            continue
        errors = np.array([rows[i][1] for i in picked])
        caps = max(1.0, MAX_CORRECTION_KG_PER_WEEK * h)
        fixes = np.clip(predicted[picked], -caps, caps)
        out[h] = (float(np.mean(np.abs(errors))), float(np.mean(np.abs(errors - fixes))), len(picked))
    return out


def format_evaluation(report):
    lines = ["Held-out error in kg (lower is better):", "  horizon   baseline   + XGBoost   change   rows"]
    for h, (base, ml, n) in report.items():
        lines.append(f"  {h:>2} wk     {base:7.2f}   {ml:9.2f}   {(ml - base) / base:+7.0%}   {n:>5}")
    return "\n".join(lines)


def importances(model, top=8):
    scores = model.get_score(importance_type="gain")
    total = sum(scores.values()) or 1.0
    return sorted(((name, value / total) for name, value in scores.items()), key=lambda p: -p[1])[:top]


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("train", "evaluate"):
        print("Usage: python weight_forecast_model.py train [--supabase] [--force] | evaluate")
        return
    if command == "train" and "--supabase" in sys.argv:
        import importlib.util

        spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
        recommender = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recommender)
        grouped = training_rows_from_supabase(recommender.supabase_client())
        source = "Supabase"
    else:
        grouped = synthetic_rows()
        source = "simulated users (bootstrap only, not real data)"
    total = sum(len(rows) for _, rows in grouped)
    print(f"{total} training rows from {len(grouped)} users: {source}.")
    if command == "train" and total < MIN_TRAINING_ROWS and "--force" not in sys.argv:
        print(f"Need at least {MIN_TRAINING_ROWS} rows; pass --force to train anyway.")
        return
    train_rows, validation_rows = split_by_user(grouped)
    model = train(train_rows, validation_rows or None)
    if validation_rows:
        print(format_evaluation(evaluate(model, validation_rows)))
    print("Most used features: " + ", ".join(f"{n} ({s:.0%})" for n, s in importances(model)))
    if command == "train":
        save_model(model)
        print(f"Saved {MODEL_PATH}.")


if __name__ == "__main__":
    main()
