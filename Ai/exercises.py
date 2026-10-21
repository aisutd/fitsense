import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "trainingdata"

FILES = {
    "Home": ["home_exercises.json"],
    "Gym": ["gym_exercises.json"],
    "Both": ["home_exercises.json", "gym_exercises.json"],
}

# Which exercise levels each proficiency may be given.
ALLOWED_LEVELS = {
    "Beginner": {"beginner"},
    "Intermediate": {"beginner", "intermediate"},
    "Advanced": {"beginner", "intermediate", "advanced", "expert"},
}


def load_exercises(location: str) -> dict[str, dict]:
    """Return {exercise_id: full exercise dict} for the user's location."""
    exercises: dict[str, dict] = {}
    for filename in FILES[location]:
        with open(DATA_DIR / filename, encoding="utf-8") as f:
            for ex in json.load(f):
                exercises.setdefault(ex["id"], ex)  # first file wins on id clash
    return exercises

CARDIO_CATEGORIES = {"cardio", "plyometrics"}
OVERLOAD_EQUIPMENT = {"machine", "cable"}

def build_shortlist(exercises: dict[str, dict], proficiency: str, goal: str,
                    max_per_muscle: int = 8) -> list[dict]:
    allowed = ALLOWED_LEVELS[proficiency]
    candidates = [e for e in exercises.values() if e.get("level") in allowed]

    # Put the exercises that fit the goal first, so the per-muscle cap
    # keeps them and drops the less relevant ones.
    if goal == "Build Muscle":
        candidates.sort(key=lambda e: e.get("equipment") not in OVERLOAD_EQUIPMENT)
    elif goal == "Lose Weight":
        candidates.sort(key=lambda e: e.get("category") not in CARDIO_CATEGORIES)

    per_group: dict[str, int] = {}
    shortlist = []
    for ex in candidates:
        # Cardio gets its own bucket so it isn't crowded out by muscle groups.
        if ex.get("category") in CARDIO_CATEGORIES:
            group = "cardio"
        else:
            group = (ex.get("primaryMuscles") or ["other"])[0]
        cap = max_per_muscle * 2 if group == "cardio" else max_per_muscle
        if per_group.get(group, 0) >= cap:
            continue
        per_group[group] = per_group.get(group, 0) + 1
        shortlist.append({
            "id": ex["id"],
            "name": ex["name"],
            "level": ex["level"],
            "equipment": ex.get("equipment"),
            "primaryMuscles": ex.get("primaryMuscles", []),
            "category": ex.get("category"),
        })
    return shortlist