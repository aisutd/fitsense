from schemas import UserProfile
from exercises import load_exercises, build_shortlist

user = UserProfile(name="Barrett", age=19, weight=165, feet=5, inches="",
                   goal="Build Muscle", proficiency="Intermediate",
                   workoutDays="4", workoutLocation="Gym")
short = build_shortlist(load_exercises(user.workout_location), user.proficiency)
print(len(short), short[:2])