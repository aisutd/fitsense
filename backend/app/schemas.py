from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gamification import PointAction


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

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=80)
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


class AwardPointsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: PointAction
    source_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="ID of what earned the points (e.g. a workout log). The same source is only rewarded once per action.",
    )


class PointsStatus(BaseModel):
    user_id: UUID
    total_points: int
    level: int
    current_level_points: int
    next_level_points: int | None
    points_to_next_level: int | None
    progress_percent: float


class AwardPointsOut(PointsStatus):
    action: PointAction
    points_awarded: int
    awarded: bool = Field(description="False when this source was already rewarded for this action")
    previous_level: int
    leveled_up: bool


class PointEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    action: str
    points: int
    source_id: str | None
    created_at: datetime


class PointActionInfo(BaseModel):
    action: PointAction
    points: int


class LevelInfo(BaseModel):
    level: int
    min_points: int
