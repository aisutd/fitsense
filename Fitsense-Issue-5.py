from pathlib import Path

profile = {}
profile_path = Path(__file__).resolve().with_name("user_Profiles.txt")

with profile_path.open("r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(
                f"{profile_path.name}, line {line_number}: expected key: value"
            )
        key, value = line.split(":", 1)
        profile[key.strip()] = value.strip()


def determine_workout(personal_goal): #Could Add level and points to the determining function but what difference would that make?
    if personal_goal.lower() == "build muscle":
        result = "Slow Weight Lifting"
        return result
    elif personal_goal.lower() == "lose weight":
        result = "Cardio Combined with full body weight lifting"
        return result
    elif personal_goal == "improve endurance":
        result = "I recommend Cardio Vascular Activity along"
        return result
    else:
        result = "General full-body fitness training"
        return result


name = profile["name"]
age = int(profile["age"])
fitness = profile["fitness_level"]
goal = profile["goal"]
days_per_week = int(profile["days_per_week"])
points = int(profile["points"])

workout = determine_workout(goal)
print (workout)


