profile = {}

with open ("user_Profiles.txt", "r") as file:
    for line in file:
        key, value = line.strip().split(":")
        profile[key] = value.strip()


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


