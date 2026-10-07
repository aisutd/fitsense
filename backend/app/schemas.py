from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FitnessGoal(str, Enum):
    lose_weight = "lose_weight"
    build_muscle = "build_muscle"
    improve_endurance = "improve_endurance"
    general_fitness = "general_fitness"
    increase_flexibility = "increase_flexibility"


class FitnessLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class WorkoutLocation(str, Enum):
    home = "home"
    gym = "gym"
    outdoors = "outdoors"
    mixed = "mixed"


class WorkoutPreference(str, Enum):
    strength = "strength"
    cardio = "cardio"
    hiit = "hiit"
    yoga = "yoga"
    pilates = "pilates"
    sports = "sports"
    calisthenics = "calisthenics"


class ProfileIn(BaseModel):
    """Onboarding answers. Height/weight are metric (cm/kg)."""

    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=13, le=100)
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    fitness_goal: FitnessGoal
    fitness_level: FitnessLevel
    workout_frequency: int = Field(ge=1, le=7, description="Workout days per week")
    workout_location: WorkoutLocation
    workout_preferences: list[WorkoutPreference] = Field(default_factory=list)

    @field_validator("height_cm", "weight_kg")
    @classmethod
    def one_decimal(cls, v: float) -> float:
        return round(v, 1)

    @field_validator("workout_preferences")
    @classmethod
    def dedupe(cls, v: list[WorkoutPreference]) -> list[WorkoutPreference]:
        return list(dict.fromkeys(v))


class ProfileOut(ProfileIn):
    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    created_at: datetime
    updated_at: datetime
