import json
from schemas import UserProfile

GOAL_RULES = {
    "Lose Weight": (
        "Emphasize cardio: include at least one cardio or plyometric exercise "
        "in every workout day, and favor circuit-style days. Keep some "
        "strength work to preserve muscle."
    ),
    "Build Muscle": (
        "Emphasize progressive overload: favor machine and cable exercises "
        "(e.g. chest flies, presses, rows) for the main work, and give each "
        "major muscle group enough weekly volume. Minimal cardio."
    ),
    # TODO: confirm these two with the personalization team
    "Endurance": "Emphasize cardio and higher-rep, lower-rest work.",
    "General Fitness": "Balance strength, cardio and core across the week.",
}

LEVEL_RULES = {
    "Beginner": "Use fixed targets like 'RIR 3' or '10-12 reps'. Never use 'failure'. 2-3 sets, 4-5 exercises per day.",
    "Intermediate": "Use 'RIR 1-2' for most sets. 'failure' only on the final set of an exercise. 3-4 sets, 5-6 exercises per day.",
    "Advanced": "RIR 0-2 and failure sets are allowed. 3-5 sets, 5-7 exercises per day.",
}

SYSTEM_PROMPT = """You are a fitness planner for the FitSense app.
Build a 7-day plan (Monday to Sunday) for the user.

Hard rules:
- Use ONLY exercise ids from the provided exercise list. Never invent ids.
- Return exactly 7 days, Monday to Sunday, in order.
- Exactly {days} days must have type "workout"; the rest must have type "rest".
- Rest days have no exercises. Put short recovery advice in "notes".
- Each workout day has a "focus" (e.g. "Push + Core") and a list of exercises.
- Each exercise has: exercise_id, sets (integer), target (string), optional note.
- Spread muscle groups sensibly across the week and avoid training the same muscle hard on back-to-back days.

Goal: {goal_rule}
Level: {level_rule}

Respond with ONLY valid JSON matching this shape, no other text:
{{"days": [{{"day": "Monday", "type": "workout", "focus": "...", "exercises": [{{"exercise_id": "...", "sets": 3, "target": "RIR 2", "note": null}}], "notes": []}}], "summary": "..."}}
"""


def build_prompt(profile: UserProfile, shortlist: list[dict]) -> tuple[str, str]:
    """Return (system_prompt, user_message)."""
    system = SYSTEM_PROMPT.format(
        days=profile.workout_days,
        goal_rule=GOAL_RULES[profile.goal],
        level_rule=LEVEL_RULES[profile.proficiency],
    )
    height = f"{profile.feet} ft" + (f" {profile.inches} in" if profile.inches is not None else "")
    user = (
        f"User: age {profile.age}, weight {profile.weight} lbs, height {height}.\n"
        f"Goal: {profile.goal}. Level: {profile.proficiency}. "
        f"Workout days per week: {profile.workout_days}. "
        f"Location: {profile.workout_location}.\n\n"
        f"Available exercises:\n{json.dumps(shortlist)}"
    )
    return system, user