from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

Goal = Literal["Lose Weight", "Build Muscle", "Endurance", "General Fitness"]
Proficiency = Literal["Beginner", "Intermediate", "Advanced"]
Location = Literal["Home", "Gym", "Both"]


class UserProfile(BaseModel):
    # Accepts the frontend's camelCase keys (workoutDays) or snake_case.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    age: int
    weight: float            # lbs
    feet: int
    inches: int | None = None
    goal: Goal
    proficiency: Proficiency
    workout_days: int        # 1-7 per week
    workout_location: Location

    @field_validator("inches", mode="before")
    @classmethod
    def empty_inches_to_none(cls, v):
        # The onboarding screen stores inches as typed, so it can be "".
        return None if v in ("", None) else v

    @field_validator("workout_days")
    @classmethod
    def days_in_range(cls, v):
        if not 1 <= v <= 7:
            raise ValueError("workout_days must be between 1 and 7")
        return v


class PlannedExercise(BaseModel):
    exercise_id: str          # must exist in the home/gym data
    sets: int
    target: str               # "RIR 2", "failure", "hold, failure"
    note: str | None = None


class DayPlan(BaseModel):
    day: str                  # "Monday"
    type: Literal["workout", "rest"]
    focus: str                # "Push + Core" or "Rest / Walk"
    exercises: list[PlannedExercise] = []
    notes: list[str] = []     # rest-day advice


class WeeklyPlan(BaseModel):
    days: list[DayPlan]       # always 7, Monday to Sunday
    summary: str | None = None