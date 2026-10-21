from schemas import WeeklyPlan, UserProfile

WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def validate_plan(plan: WeeklyPlan, profile: UserProfile, valid_ids: set[str]) -> list[str]:
    """Return a list of problems. An empty list means the plan is good."""
    errors = []

    if [d.day for d in plan.days] != WEEK:
        errors.append("Days must be Monday to Sunday, in order.")

    workout_days = [d for d in plan.days if d.type == "workout"]
    if len(workout_days) != profile.workout_days:
        errors.append(f"Expected {profile.workout_days} workout days, got {len(workout_days)}.")

    for d in plan.days:
        if d.type == "rest" and d.exercises:
            errors.append(f"{d.day} is a rest day but has exercises.")
        for ex in d.exercises:
            if ex.exercise_id not in valid_ids:
                errors.append(f"{d.day}: unknown exercise id '{ex.exercise_id}'.")
            if profile.proficiency == "Beginner" and "failure" in ex.target.lower():
                errors.append(f"{d.day}: beginners shouldn't train to failure ({ex.exercise_id}).")

    return errors