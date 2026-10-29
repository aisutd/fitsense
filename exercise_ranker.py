"""XGBoost ranker that orders the exercises the rules in Fitsense-Issue-5.py allow.

The rules still decide what is safe and available (level, equipment, goal). The model only
decides the order, by predicting how likely this user is to complete a plan that includes the
exercise. Training data comes from Supabase: plan_exercises -> workout_plans -> workout_logs.

    python exercise_ranker.py train            # fetch from Supabase, train, save MODEL_PATH
    python exercise_ranker.py train --force    # train even with less than MIN_TRAINING_ROWS

Until a model file exists, recommendations fall back to the rule-based order.
"""

from pathlib import Path
import sys

import numpy as np

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "exercise_ranker.json"
# Below this many labeled (user, exercise) rows a model mostly memorizes noise.
MIN_TRAINING_ROWS = 200
# Supabase returns at most 1000 rows per request (its "Max rows" API setting), so reads are paged.
PAGE_SIZE = 1000

LEVELS = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 2}
GOALS = ["build_muscle", "lose_weight", "improve_endurance", "general_fitness", "increase_flexibility"]
LOCATIONS = ["home", "gym", "outdoors", "mixed"]
CATEGORIES = ["strength", "powerlifting", "olympic weightlifting", "strongman",
              "cardio", "plyometrics", "stretching"]
FORCES = ["push", "pull", "static"]
MUSCLES = ["abdominals", "abductors", "adductors", "biceps", "calves", "chest", "forearms",
           "glutes", "hamstrings", "lats", "lower back", "middle back", "neck", "quadriceps",
           "shoulders", "traps", "triceps"]
PREFERENCES = ["strength", "cardio", "hiit", "yoga", "pilates", "sports", "calisthenics"]

FEATURE_NAMES = (
    ["age", "user_level", "workout_frequency", "exercise_level", "level_gap", "compound",
     "needs_equipment", "secondary_muscle_count"]
    + [f"goal={g}" for g in GOALS]
    + [f"location={l}" for l in LOCATIONS]
    + [f"prefers={p}" for p in PREFERENCES]
    + [f"category={c}" for c in CATEGORIES]
    + [f"force={f}" for f in FORCES]
    + [f"primary={m}" for m in MUSCLES]
)


def one_hot(value, options):
    return [1.0 if value == option else 0.0 for option in options]


def features(profile, exercise):
    """One numeric row describing a (user, exercise) pair, in FEATURE_NAMES order."""
    user_level = LEVELS[profile["fitness_level"]]
    exercise_level = LEVELS[exercise["level"]]
    preferences = set(profile.get("workout_preferences") or [])
    primary = set(exercise["primaryMuscles"])
    return (
        [float(profile["age"]), float(user_level), float(profile["workout_frequency"]),
         float(exercise_level), float(user_level - exercise_level),
         1.0 if exercise["mechanic"] == "compound" else 0.0,
         0.0 if exercise["equipment"] in (None, "body only") else 1.0,
         float(len(exercise["secondaryMuscles"]))]
        + one_hot(profile["fitness_goal"], GOALS)
        + one_hot(profile["workout_location"], LOCATIONS)
        + [1.0 if p in preferences else 0.0 for p in PREFERENCES]
        + one_hot(exercise["category"], CATEGORIES)
        + one_hot(exercise["force"], FORCES)
        + [1.0 if m in primary else 0.0 for m in MUSCLES]
    )


def train(rows):
    """Fit a model on (profile, exercise, completed) rows. completed is 0 or 1."""
    import xgboost as xgb

    X = np.array([features(profile, exercise) for profile, exercise, _ in rows])
    y = np.array([completed for _, _, completed in rows])
    if len(set(y)) < 2:
        raise ValueError("Training data needs both completed and skipped examples.")
    # Shallow trees and a little regularization: the dataset is small and noisy.
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 3, "eta": 0.05,
              "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 2, "lambda": 1.0,
              "seed": 0}
    return xgb.train(params, xgb.DMatrix(X, label=y, feature_names=FEATURE_NAMES), num_boost_round=200)


def save_model(model, path=MODEL_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))


def load_model(path=MODEL_PATH):
    """The saved model, or None if none has been trained yet."""
    if not path.exists():
        return None
    import xgboost as xgb

    return xgb.Booster(model_file=str(path))


def scores(model, profile, exercises):
    """Predicted completion probability for each exercise, in the same order."""
    if not exercises:
        return []
    import xgboost as xgb

    X = np.array([features(profile, exercise) for exercise in exercises])
    return model.predict(xgb.DMatrix(X, feature_names=FEATURE_NAMES)).tolist()


def fetch_all(client, table, columns, key, user_id=None):
    """Every row of a table (or one user's rows), read PAGE_SIZE rows at a time in key order.

    Stops on an empty page rather than a short one, so it still reads everything if the
    project's max-rows setting is below PAGE_SIZE.
    """
    rows = []
    while True:
        query = client.table(table).select(columns)
        if user_id is not None:
            query = query.eq("user_id", user_id)
        page = query.order(key).range(len(rows), len(rows) + PAGE_SIZE - 1).execute().data
        if not page:
            return rows
        rows.extend(page)


def training_rows_from_supabase(client, profile_from_row, exercises):
    """Label every exercise in a logged plan with whether the user completed that plan.

    plan_exercises points at Supabase's exercises table, so exercises are matched to the
    JSON data by name. Plans with no workout_logs yet are left out: no outcome is known.
    """
    by_name = {e["name"].strip().lower(): e for e in exercises["home"] + exercises["gym"]}
    profiles = {
        row["user_id"]: profile_from_row(row)
        for row in fetch_all(client, "profiles",
                             "*, user_preferences(available_equipment), user_gamification(total_xp)",
                             "user_id")
    }
    outcomes = {}
    for log in fetch_all(client, "workout_logs", "plan_id, completion_status", "workout_log_id"):
        if log["plan_id"]:
            done = log["completion_status"] == "completed"
            outcomes[log["plan_id"]] = outcomes.get(log["plan_id"], False) or done
    plan_exercises = fetch_all(client, "plan_exercises",
                               "plan_id, workout_plans(user_id), exercises(name)", "plan_exercise_id")

    rows = []
    for item in plan_exercises:
        plan = item.get("workout_plans") or {}
        exercise = by_name.get(((item.get("exercises") or {}).get("name") or "").strip().lower())
        profile = profiles.get(plan.get("user_id"))
        if item["plan_id"] in outcomes and exercise and profile:
            rows.append((profile, exercise, int(outcomes[item["plan_id"]])))
    return rows


def main():
    if sys.argv[1:2] != ["train"]:
        print("Usage: python exercise_ranker.py train [--force]")
        return
    import importlib.util

    spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
    recommender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recommender)

    rows = training_rows_from_supabase(recommender.supabase_client(),
                                       recommender.profile_from_supabase_row,
                                       recommender.load_exercises())
    print(f"{len(rows)} labeled (user, exercise) rows.")
    if len(rows) < MIN_TRAINING_ROWS and "--force" not in sys.argv:
        print(f"Need at least {MIN_TRAINING_ROWS} to train (or pass --force). "
              "Recommendations keep using the rule-based order.")
        return
    save_model(train(rows))
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
