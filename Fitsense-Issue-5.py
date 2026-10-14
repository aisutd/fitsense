from pathlib import Path

def create_profile(filename):
    user_name = input("Enter your name: ")
    while True:
        try:
            user_age = int(input("Enter your age: "))
            if user_age <= 0:
                print("Age must be greater than zero.")
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
    with open(filename, "w") as file:
        file.write(f"name: {user_name}\n")
        file.write(f"age: {user_age}\n")
        file.write(f"fitness_level: {fitness_level}\n")
        file.write(f"goal: {user_goal}\n")
        file.write(f"days_per_week: {days_per_week}\n")
        file.write(f"location: {location}\n")
        file.write(f"weight: {weight} lbs\n")
        file.write("points: 0\n")

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

    # Convert weight to a number and keep its unit
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

def determine_workout(profile, workouts):
    # Get information from the saved profile
    name = profile["name"]
    age = profile["age"]
    fitness = profile["fitness_level"].strip().lower()
    goal = profile["goal"].strip().upper()
    location = profile["location"].strip().upper()
    weight = profile["weight"]
    weight_unit = profile["weight_unit"]

    # Match the goal names used in Workouts.txt
    if goal == "BUILD MUSCLE":
        goal = "BUILDING MUSCLE"
    elif goal == "GENERAL FITNESS":
        goal = "GENERAL BODY FITNESS"

    # Validate the selected goal
    if goal not in workouts:
        print("Fitness goal not found.")
        return

    # Validate the selected location
    if location not in workouts[goal]:
        print("No workouts found for this goal and location.")
        return

    # Display user information
    print("\n========== FIT-SENSE WORKOUT ==========")
    print(f"Name: {name}")
    print(f"Age: {age}")
    print(f"Fitness level: {fitness.title()}")
    print(f"Goal: {goal}")
    print(f"Location: {location}")
    print(f"Weight: {weight:g} {weight_unit}")
    print(f"Workout days per week: {profile['days_per_week']}")

    selected_workouts = workouts[goal][location]

    # Display Upper Body and Lower Body workouts
    for category in ["Upper Body", "Lower Body"]:
        print(f"\n--- {category} ---")

        exercises = selected_workouts.get(category, [])

        if not exercises:
            print("No exercises available for this category.")
            continue

        for exercise in exercises:
            exercise_name = exercise["name"]
            equipment = exercise["equipment"]

            print(f"\nExercise: {exercise_name}")
            print(f"Equipment: {equipment}")

            # Cardio exercises use duration rather than reps
            cardio_keywords = [
                "running",
                "walking",
                "bicycling",
                "bike",
                "elliptical",
                "stairmaster"
            ]

            if any(word in exercise_name.lower()
                   for word in cardio_keywords):
                print("Suggested duration: 10-20 minutes, as tolerated")

            elif goal == "IMPROVE ENDURANCE":
                print("Suggested reps: 12-15")

            elif age < 18:
                print("Suggested reps: 8-12, with appropriate supervision")

            elif age >= 60:
                print("Suggested reps: 8-12, as tolerated")

            elif goal == "BUILDING MUSCLE":
                if fitness == "beginner":
                    print("Suggested reps: 8-12")
                elif fitness == "intermediate":
                    print("Suggested reps: 8-12")
                else:
                    print("Suggested reps: 6-12")

            elif goal == "LOSE WEIGHT":
                print("Suggested reps: 10-15")

            else:
                print("Suggested reps: 8-12")

    print("\n======================================")



print("=== Welcome to Fit-sense ===")
while True:
    try:
        choose = int(input(
            "Create a new profile (1) or access an existing profile (2)? "
        ))

        if choose in [1, 2]:
            break

        print("Please enter 1 or 2.")

    except ValueError:
        print("Please enter a valid number.")

if choose == 1:
    create_profile("user_Profiles.txt")


profile = load_profile("user_Profiles.txt")
workouts = load_workout("Workouts.txt")

determine_workout(profile, workouts)




