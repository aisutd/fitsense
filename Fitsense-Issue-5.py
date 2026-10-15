from pathlib import Path
import json
import sys

def create_profile(filename):
    user_name = input("Enter your name: ")
    while True:
        try:
            user_age = int(input("Enter your age: "))
            if user_age <= 0:
                print("Age must be greater than zero.")
                continue
            break
        except ValueError:
            print("Please print a valid whole number")
    while True:
        fitness_level = input("Enter fitness level (Beginner, Intermediate, Advanced): ").strip().title()
        if fitness_level in ["Beginner", "Intermediate", "Advanced"]:
            break
        print("Please select Beginner, Intermediate, or Advanced.")
    while True:
        user_goal = input(
            "Enter goal (Building Muscle, Lose Weight, "
            "Improve Endurance, General Body Fitness): "
        ).strip().title()
        valid_goals = [
            "Building Muscle",
            "Lose Weight",
            "Improve Endurance",
            "General Body Fitness"
        ]
        if user_goal in valid_goals:
            break
        print("Please enter one of the listed goals.")
    while True:
        try:
            days_per_week = int(
                input("How many days per week will you work out? ")
            )

            if 1 <= days_per_week <= 7:
                break

            print("Enter a number between 1 and 7.")

        except ValueError:
            print("Please enter a valid whole number.")

    while True:
        location = input("Preferred location (HOME or GYM): ").strip().upper()

        if location in ["HOME", "GYM"]:
            break

        print("Please enter HOME or GYM.")

    while True:
        try:
            weight = float(input("Enter your weight in lbs: "))

            if weight > 0:
                break

            print("Weight must be greater than zero.")

        except ValueError:
            print("Please enter a valid number.")
    equipment = prompt_equipment()
    with open(filename, "w") as file:
        file.write(f"name: {user_name}\n")
        file.write(f"age: {user_age}\n")
        file.write(f"fitness_level: {fitness_level}\n")
        file.write(f"goal: {user_goal}\n")
        file.write(f"days_per_week: {days_per_week}\n")
        file.write(f"location: {location}\n")
        file.write(f"weight: {weight} lbs\n")
        file.write("points: 0\n")
        file.write(f"equipment: {', '.join(equipment) or 'none'}\n")

    print("\nProfile saved successfully!")



def load_profile(filename):
    profile = {}

    with open(filename, "r") as file:
        for line in file:
            if ":" in line:
                key, value = line.strip().split(":", 1)
                profile[key.strip().lower()] = value.strip()

    profile["age"] = int(profile["age"])
    profile["days_per_week"] = int(profile["days_per_week"])
    profile["points"] = int(profile["points"])


    weight_info = profile["weight"].split()
    profile["weight"] = float(weight_info[0])
    profile["weight_unit"] = (
        weight_info[1] if len(weight_info) > 1 else "lbs"
    )

    return profile

def load_workout(filename):
    workouts = {}

    current_goal = None
    current_location = None
    current_category = None
    supplemental_section = False

    goals = [
        "BUILDING MUSCLE",
        "LOSE WEIGHT",
        "IMPROVE ENDURANCE",
        "GENERAL BODY FITNESS"
    ]

    categories = [
        "UPPER BODY",
        "LOWER BODY",
        "CORE",
        "FULL BODY"
    ]

    with open(filename, "r") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            if line.upper() == "SUPPLEMENTAL CORE FOR ALL GOALS":
                supplemental_section = True
                continue

            if supplemental_section:
                continue

            if line.upper() in goals:
                current_goal = line.upper()
                workouts.setdefault(current_goal, {})
                current_location = None
                current_category = None
                continue

            if line.upper() in ["HOME", "GYM"] and current_goal:
                current_location = line.upper()

                workouts[current_goal].setdefault(
                    current_location, {}
                )

                current_category = None
                continue

            if line.upper() in categories and current_location:
                current_category = line.title()

                workouts[current_goal][current_location].setdefault(
                    current_category, []
                )
                continue

            if line.startswith("- ") and current_category:
                exercise_info = line[2:].split("|", 1)

                exercise_name = exercise_info[0].strip()
                equipment = "Not specified"

                if len(exercise_info) > 1:
                    equipment_text = exercise_info[1].strip()

                    if equipment_text.lower().startswith("equipment:"):
                        equipment = equipment_text.split(":", 1)[1].strip()

                workouts[current_goal][current_location][
                    current_category
                ].append({
                    "name": exercise_name,
                    "equipment": equipment
                })

    return workouts


BASE_DIR = Path(__file__).resolve().parent
EQUIPMENT_CHOICES = {
    "dumbbells", "resistance_bands", "barbell", "plates", "bench", "rack",
    "stable_support", "cable_station", "chest_press_machine",
    "shoulder_press_machine", "leg_press_machine", "leg_extension_machine",
    "leg_curl_machine", "calf_raise_machine", "treadmill", "exercise_bike",
    "elliptical", "stairmaster", "rowing_machine", "jump_rope",
}
LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}


def parse_equipment(value):
    if isinstance(value, str):
        value = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError("Equipment must be a list or comma-separated names.")
    selected = {item.strip().lower() for item in value}
    if "none" in selected:
        if len(selected) > 1:
            raise ValueError("Select none on its own, or list your equipment.")
        selected = set()
    unknown = selected - EQUIPMENT_CHOICES
    if unknown:
        raise ValueError(f"Unknown equipment: {', '.join(sorted(unknown))}")
    return sorted(selected)


def prompt_equipment():
    print("Equipment choices: " + ", ".join(sorted(EQUIPMENT_CHOICES)))
    while True:
        try:
            return parse_equipment(input("Available equipment (comma-separated, or none): "))
        except ValueError as error:
            print(error)


def recommend_exercises(profile, workouts, catalog):
    """Return up to three matching candidates per category, not a full prescription."""
    level = profile["fitness_level"].strip().lower()
    if level not in LEVEL_RANK:
        raise ValueError("Fitness level must be Beginner, Intermediate, or Advanced.")
    goal = profile["goal"].strip().upper()
    goal = {"BUILD MUSCLE": "BUILDING MUSCLE", "GENERAL FITNESS": "GENERAL BODY FITNESS"}.get(goal, goal)
    location = profile["location"].strip().upper()
    if goal not in workouts or location not in workouts[goal]:
        raise ValueError("No exercise catalog for this goal and location.")
    available = set(parse_equipment(profile.get("equipment", "none")))
    result = {}
    for category, exercises in workouts[goal][location].items():
        matches = []
        for exercise in exercises:
            metadata = catalog.get(exercise["name"])
            if metadata is None:
                continue 
            rank = LEVEL_RANK[metadata["minimum_level"]]
            required = set(metadata["required_equipment"])
            if rank <= LEVEL_RANK[level] and required <= available:
                matches.append({
                    **exercise,
                    **metadata,
                    "reason": f"Matches {goal.title()}, is tagged {metadata['minimum_level']} or above, and all required equipment is available.",
                })

        matches.sort(key=lambda item: (-LEVEL_RANK[item["minimum_level"]], item["name"]))
        if matches:
            result[category] = matches[:3]
    return result


def determine_workout(profile, workouts, catalog=None):
    if catalog is None:
        catalog = json.loads((BASE_DIR / "exercise_metadata.json").read_text())
    selected = recommend_exercises(profile, workouts, catalog)
    print("\n========== FIT-SENSE WORKOUT ==========")
    print(f"Fitness level: {profile['fitness_level']}")
    print(f"Goal: {profile['goal']} | Location: {profile['location']}")
    print(f"Available equipment: {', '.join(parse_equipment(profile.get('equipment', 'none'))) or 'none'}")
    print("Exercise candidates — difficulty tags are provisional.")
    for category, exercises in selected.items():
        print(f"\n--- {category} ---")
        for exercise in exercises:
            print(f"- {exercise['name']}")
            print(f"  Required: {', '.join(exercise['required_equipment']) or 'none'}")
            print(f"  Why: {exercise['reason']}")
    if not selected:
        print("No matching exercises. Update equipment or review the exercise catalog.")
    return selected


def demo(workouts):
    base = {"fitness_level": "Beginner", "goal": "Building Muscle", "location": "HOME", "equipment": []}
    comparisons = [
        ("Baseline", base),
        ("Change only fitness level", {**base, "fitness_level": "Intermediate"}),
        ("Change only goal", {**base, "goal": "Improve Endurance"}),
        ("Change only equipment", {**base, "equipment": ["dumbbells"]}),
    ]
    for label, profile in comparisons:
        print(f"\nDEMO: {label}")
        determine_workout(profile, workouts)


def main():
    workouts = load_workout(BASE_DIR / "Workout.txt")
    if "--demo" in sys.argv:
        demo(workouts)
        return
    print("=== Welcome to Fit-sense ===")
    while True:
        choose = input("Create a new profile (1) or access an existing profile (2)? ").strip()
        if choose in {"1", "2"}:
            break
        print("Please enter 1 or 2.")
    profile_path = BASE_DIR / "user_Profiles.txt"
    if choose == "1":
        create_profile(profile_path)
    profile = load_profile(profile_path)
    if "equipment" not in profile:
        print("This saved profile does not have equipment information yet.")
        profile["equipment"] = prompt_equipment()
    determine_workout(profile, workouts)


if __name__ == "__main__":
    main()
