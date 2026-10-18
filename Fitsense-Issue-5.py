"""FitSense workout recommender.

User profiles come from Supabase; exercises come from home.json and gym.json.

    python Fitsense-Issue-5.py --user <supabase user_id>
"""

from pathlib import Path
import json
import os
import sys
import uuid

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


def load_profile_from_supabase(user_id):
    """Fetch a user's profile, saved equipment and points from Supabase."""
    from supabase import create_client

    load_env(BASE_DIR / ".env")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in .env (see .env.example).")

    client = create_client(url, key)
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
        "fitness_level": row["fitness_level"],
        "fitness_goal": row["fitness_goal"],
        "workout_location": row["workout_location"],
        "workout_frequency": row["workout_frequency"],
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


def recommend_exercises(profile, exercises):
    """Return up to PER_GROUP matching exercises per muscle group."""
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
        result[group] = matches[:PER_GROUP]
    return result


def print_workout(profile, selected):
    print("\n========== FIT-SENSE WORKOUT ==========")
    print(f"{profile['name']} | {profile['points']} points")
    print(f"Level: {profile['fitness_level']} | Goal: {profile['fitness_goal']} | "
          f"Location: {profile['workout_location']} | {profile['workout_frequency']} days/week")
    print(f"Saved equipment: {', '.join(profile['equipment']) or 'none'}")
    for group, exercises in selected.items():
        print(f"\n--- {group} ---")
        for exercise in exercises:
            print(f"- {exercise['name']} ({exercise['level']}, {exercise['equipment'] or 'no equipment'})")
    if not selected:
        print("No matching exercises. Add equipment in user_preferences or change the goal.")


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
    print_workout(profile, recommend_exercises(profile, load_exercises()))


if __name__ == "__main__":
    main()
