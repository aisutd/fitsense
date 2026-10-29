"""FitSense workout recommender.

User profiles come from Supabase; exercises come from home.json and gym.json. Prints this week's saved
plan (see weekly_plan.py), building and saving it first if there is none. After the workout
it prints the user's weekly progress forecast (see progress_forecast.py).

    python Fitsense-Issue-5.py --user <supabase user_id>
"""

from pathlib import Path
import json
import os
import sys
import uuid

import exercise_ranker
import progress_forecast

BASE_DIR = Path(__file__).resolve().parent

# Supabase uses beginner/intermediate/advanced; the exercise data uses expert for the top level.
LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2, "expert": 2}

# Exercise categories that serve each Supabase fitness_goal.
GOAL_CATEGORIES = {
    "build_muscle": {"strength", "powerlifting", "olympic weightlifting", "strongman"},
    "lose_weight": {"cardio", "plyometrics", "strength"},
    "improve_endurance": {"cardio", "plyometrics"},
    "general_fitness": {"strength", "cardio", "stretching"},
    "increase_flexibility": {"stretching"},
}

MUSCLE_GROUPS = {
    "Upper Body": {"chest", "shoulders", "biceps", "triceps", "lats", "middle back",
                   "traps", "forearms", "neck"},
    "Lower Body": {"quadriceps", "hamstrings", "glutes", "calves", "adductors", "abductors"},
    "Core": {"abdominals", "lower back"},
}

# Needs nothing to own: always available for home and outdoor workouts.
NO_EQUIPMENT = {None, "body only"}
HOME_EQUIPMENT = {"bands", "dumbbell", "kettlebells", "medicine ball", "exercise ball",
                  "foam roll", "other"}
PER_GROUP = 3

# Dose by age group and fitness level. Sources:
# - HHS Physical Activity Guidelines for Americans, 2nd ed. (2018): weekly aerobic minutes for
#   adults and older adults; 60 min/day of activity for ages 6-17.
# - ACSM Position Stand, Progression Models in Resistance Training (2009): novices 1-3 sets of
#   8-12 reps; intermediate/advanced multiple sets, mostly 6-12 reps.
# - ACSM/AHA Physical Activity in Older Adults (2007): 1-3 sets of 10-15 reps at moderate effort.
# - ACSM youth resistance training guidance: 1-3 sets of 6-15 reps, starting light at 10-15.
# - ACSM flexibility guidance: hold 10-30 s (30-60 s for older adults), 2-4 times per stretch.
# - Plyometrics have no federal guideline; these follow NSCA's low-volume starting advice.
STRENGTH_DOSE = {  # (sets, reps), each (low, high)
    "youth":  {"beginner": ((1, 2), (10, 15)), "intermediate": ((2, 3), (8, 12)), "advanced": ((2, 3), (6, 12))},
    "adult":  {"beginner": ((1, 3), (8, 12)), "intermediate": ((3, 3), (6, 12)), "advanced": ((3, 5), (6, 12))},
    "senior": {"beginner": ((1, 1), (10, 15)), "intermediate": ((1, 2), (10, 15)), "advanced": ((2, 3), (8, 12))},
}
PLYOMETRIC_DOSE = {
    "youth":  {"beginner": ((1, 2), (5, 8)), "intermediate": ((2, 3), (6, 8)), "advanced": ((3, 3), (6, 10))},
    "adult":  {"beginner": ((2, 2), (5, 8)), "intermediate": ((3, 3), (6, 10)), "advanced": ((3, 4), (8, 12))},
    "senior": {"beginner": ((1, 1), (5, 5)), "intermediate": ((1, 2), (5, 8)), "advanced": ((2, 2), (6, 8))},
}
STRETCH_HOLD = {"youth": "10-30 s", "adult": "10-30 s", "senior": "30-60 s"}
STRETCH_SETS = (2, 4)
# Weekly aerobic minutes (HHS). Beginners start at the minimum; advanced use vigorous effort.
CARDIO_WEEKLY = {
    "beginner": ("moderate", 150, 150),
    "intermediate": ("moderate", 150, 300),
    "advanced": ("vigorous", 75, 150),
}
YOUTH_CARDIO_MINUTES = 60  # HHS: 60 min of activity every day
SESSION_MINUTES = (20, 60)  # ACSM's per-session aerobic range


def age_group(age):
    if age < 18:
        return "youth"
    if age >= 65:
        return "senior"
    return "adult"


def session_minutes(weekly, days):
    low, high = SESSION_MINUTES
    return min(max(round(weekly / days), low), high)


def dose_range(profile, exercise, days):
    """{"sets", "reps", "minutes"}: (low, high) or None, by age group and level, in a days-day week."""
    group = age_group(profile["age"])
    level = profile["fitness_level"]
    category = exercise["category"]
    if category == "stretching":
        return {"sets": STRETCH_SETS, "reps": None, "minutes": None}
    if category == "cardio":
        if group == "youth":
            return {"sets": None, "reps": None, "minutes": (YOUTH_CARDIO_MINUTES, YOUTH_CARDIO_MINUTES)}
        _, low, high = CARDIO_WEEKLY[level]
        return {"sets": None, "reps": None, "minutes": (session_minutes(low, days), session_minutes(high, days))}
    sets, reps = (PLYOMETRIC_DOSE if category == "plyometrics" else STRENGTH_DOSE)[group][level]
    return {"sets": sets, "reps": reps, "minutes": None}


def load_env(filename):
    """Read KEY=value lines from .env without overriding variables already set."""
    if not filename.exists():
        return
    with open(filename, "r") as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def load_exercises():
    return {
        "home": json.loads((BASE_DIR / "home.json").read_text()),
        "gym": json.loads((BASE_DIR / "gym.json").read_text()),
    }


def supabase_client():
    from supabase import create_client

    load_env(BASE_DIR / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in .env (see .env.example).")
    return create_client(url, key)


def load_profile_from_supabase(user_id):
    """Fetch a user's profile, saved equipment and points from Supabase."""
    client = supabase_client()
    # Equipment lives in user_preferences and points in user_gamification (one row per user each).
    response = (
        client.table("profiles")
        .select("*, user_preferences(available_equipment), user_gamification(total_xp)")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise LookupError(f"No profile found for user {user_id}.")
    return profile_from_supabase_row(response.data[0])


def profile_from_supabase_row(row):
    preferences = row.get("user_preferences") or {}
    gamification = row.get("user_gamification") or {}
    return {
        "user_id": row["user_id"],
        "name": row.get("name") or row["user_id"],
        "age": int(row["age"]),
        "fitness_level": row["fitness_level"],
        "fitness_goal": row["fitness_goal"],
        "workout_location": row["workout_location"],
        "workout_frequency": row["workout_frequency"],
        "workout_preferences": row.get("workout_preferences") or [],
        "equipment": sorted({item.strip().lower() for item in preferences.get("available_equipment") or []}),
        "points": int(gamification.get("total_xp") or 0),  # no row until the user earns points
    }


def candidate_exercises(profile, exercises):
    """Exercises the user can do where they train, with the equipment they have."""
    location = profile["workout_location"]
    if location in ("gym", "mixed"):
        return exercises["home"] + exercises["gym"]  # a gym covers everything home does
    owned = set(profile["equipment"]) & HOME_EQUIPMENT
    if location == "outdoors":
        owned = set()
    return [e for e in exercises["home"] if e["equipment"] in NO_EQUIPMENT or e["equipment"] in owned]


def muscle_group(exercise):
    if exercise["category"] == "cardio":
        return "Cardio"
    if exercise["category"] == "stretching":
        return "Mobility"
    primary = set(exercise["primaryMuscles"])
    for group, muscles in MUSCLE_GROUPS.items():
        if primary & muscles:
            return group
    return "Full Body"


def recommend_exercises(profile, exercises, model=None, per_group=PER_GROUP):
    """Return up to per_group matching exercises per muscle group (all of them for None).

    With a trained XGBoost model (see exercise_ranker.py), each group is ordered by the user's
    predicted chance of completing it; the rule-based order breaks ties and is used without one.
    """
    level = LEVEL_RANK[profile["fitness_level"]]
    categories = GOAL_CATEGORIES[profile["fitness_goal"]]
    groups = {}
    for exercise in candidate_exercises(profile, exercises):
        if exercise["category"] in categories and LEVEL_RANK[exercise["level"]] <= level:
            groups.setdefault(muscle_group(exercise), []).append(exercise)

    result = {}
    for group, matches in groups.items():
        # Closest to the user's level first, compound movements before isolation.
        matches.sort(key=lambda e: (-LEVEL_RANK[e["level"]], e["mechanic"] != "compound", e["name"]))
        if model is not None:
            predicted = exercise_ranker.scores(model, profile, matches)
            # sorted() is stable, so equal scores keep the rule-based order.
            matches = [e for _, e in sorted(zip(predicted, matches), key=lambda pair: -pair[0])]
        result[group] = matches[:per_group]
    return result


def main():
    if "--user" not in sys.argv or sys.argv.index("--user") + 1 >= len(sys.argv):
        print("Usage: python Fitsense-Issue-5.py --user <supabase user_id>")
        return
    user_id = sys.argv[sys.argv.index("--user") + 1]
    try:
        uuid.UUID(user_id)
    except ValueError:
        print(f"{user_id} is not a valid user_id (expected a full UUID from the profiles table).")
        return
    try:
        profile = load_profile_from_supabase(user_id)
    except LookupError as error:
        print(error)
        return
    import weekly_plan  # imported here: weekly_plan loads this file as its recommender

    model = exercise_ranker.load_model()
    client = supabase_client()
    print(weekly_plan.format_plan(profile, weekly_plan.current_plan(client, profile, load_exercises(), model=model)))
    print("\nOrdered by the XGBoost ranker." if model else
          "\nNo trained ranker yet (python exercise_ranker.py train); using the rule-based order.")
    print(progress_forecast.format_forecast(progress_forecast.forecast_from_supabase(client, user_id)))


if __name__ == "__main__":
    main()
