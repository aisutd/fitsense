from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


# --- HealthScore ---------------------------------------------------------------

class HealthScoreRange(str, Enum):
    week = "week"            # last 7 days, including end_date
    last_week = "last-week"  # the 7 days before that
    month = "month"          # last 30 days, including end_date


class DateRange(BaseModel):
    key: HealthScoreRange
    start: date
    end: date
    days: int


class CategoryScore(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: int | None
    available: bool
    reason: str | None = Field(default=None, description="Why the category is unavailable")


class HealthScoreOut(BaseModel):
    user_id: UUID
    range: DateRange
    overall_score: int | None = Field(description="Null when no category has enough data")
    workouts: int | None
    nutrition: int | None
    sleep: int | None
    activity: int | None
    provisional: bool = Field(description="True when calculated from only some categories")
    available_categories: list[str]
    weights: dict[str, float]
    categories: dict[str, CategoryScore]
    disclaimer: str


class HealthScoreSnapshotOut(HealthScoreOut):
    score_id: UUID
    calculated_at: datetime


class HealthScoreHistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score_id: UUID
    score: float | None
    workout_score: float | None
    nutrition_score: float | None
    sleep_score: float | None
    activity_score: float | None
    provisional: bool
    range_start: date | None
    range_end: date | None
    calculated_at: datetime


# --- Logging & goals -------------------------------------------------------------

class CompletionStatus(str, Enum):
    completed = "completed"
    partial = "partial"
    skipped = "skipped"


class WorkoutLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workout_date: date
    completion_status: CompletionStatus = CompletionStatus.completed
    duration_minutes: int | None = Field(default=None, ge=0, le=600)
    plan_id: UUID | None = None


class SleepLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hours_slept: float = Field(ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)


class ActivityLogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: int | None = Field(default=None, ge=0, le=200_000)
    active_minutes: int | None = Field(default=None, ge=0, le=1440)
    calories_burned: int | None = Field(default=None, ge=0, le=20_000)

    @model_validator(mode="after")
    def steps_or_minutes(self):
        if self.steps is None and self.active_minutes is None:
            raise ValueError("steps or active_minutes is required")
        return self


class MealType(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class MealLogIn(BaseModel):
    """A confirmed meal from the NLP + FoodData Central pipeline.

    Nutrition values must be calculated from the food database using the
    confirmed quantities - not estimated by a language model.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    log_date: date
    meal_type: MealType | None = None
    raw_text: str | None = Field(default=None, max_length=500)
    display_name: str | None = Field(default=None, max_length=120)
    calories: float = Field(ge=0, le=10_000)
    protein_g: float = Field(ge=0, le=1_000)
    carbs_g: float = Field(ge=0, le=2_000)
    fat_g: float = Field(ge=0, le=1_000)


class NutritionGoalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_calorie_target: int = Field(ge=800, le=10_000)
    protein_target_g: float | None = Field(default=None, ge=0, le=1_000)
    carbs_target_g: float | None = Field(default=None, ge=0, le=2_000)
    fat_target_g: float | None = Field(default=None, ge=0, le=1_000)
    water_target_ml: int | None = Field(default=None, ge=0, le=10_000)


class GoalsIn(BaseModel):
    """Any subset of goals; omitted ones are left unchanged."""

    model_config = ConfigDict(extra="forbid")

    nutrition: NutritionGoalIn | None = None
    sleep_target_hours: float | None = Field(default=None, ge=4, le=12)
    daily_steps: int | None = Field(default=None, ge=1000, le=100_000)
    daily_active_minutes: int | None = Field(default=None, ge=5, le=600)


class GoalsOut(BaseModel):
    nutrition: dict = Field(description="calories, protein_g, carbs_g, fat_g targets")
    nutrition_estimated: bool = Field(description="True when estimated from the profile because no goal is set")
    sleep_target_hours: float
    daily_steps: int
    daily_active_minutes: int


# --- Accounts (testing login) ------------------------------------------------------

class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,30}$", description="3-30 letters, numbers, _ . or -")
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class AccountOut(BaseModel):
    user_id: UUID
    username: str
    has_profile: bool = Field(description="False until onboarding has been completed")


# --- Food logging ----------------------------------------------------------------

UnitName = Literal[
    "count", "g", "kg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "slice", "piece", "serving", "bowl",
    "plate", "glass", "can", "bottle", "handful", "scoop", "bag", "bar", "small", "medium", "large",
]


class AnalyzeMealIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=2, max_length=500, description="e.g. 'I had a 3-egg omelette for breakfast'")
    log_date: date
    meal_type: MealType | None = Field(default=None, description="Overrides the meal type detected in the text")


class MealItemUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: float | None = Field(default=None, gt=0, le=5000)
    unit: UnitName | None = None
    fdc_id: int | None = Field(default=None, gt=0, description="Swap to this FoodData Central food")


class MealItemAddIn(BaseModel):
    """Either typed text ("2 tbsp sour cream") or a food picked from search (fdc_id)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str | None = Field(default=None, min_length=2, max_length=200)
    fdc_id: int | None = Field(default=None, gt=0, description="A food picked from /foods/suggest or /foods/search")
    quantity: float | None = Field(default=None, gt=0, le=5000)
    unit: UnitName | None = None

    @model_validator(mode="after")
    def _text_or_food(self):
        if self.text is None and self.fdc_id is None:
            raise ValueError("Give the ingredient text or pick a food (fdc_id)")
        return self


class MealStartIn(BaseModel):
    """A meal started from foods picked in the search box."""
    model_config = ConfigDict(extra="forbid")

    log_date: date
    meal_type: MealType | None = None
    items: list[MealItemAddIn] = Field(min_length=1, max_length=30)


class FoodRef(BaseModel):
    fdc_id: int
    description: str


class FoodSearchHit(BaseModel):
    fdc_id: int
    description: str
    data_type: str
    calories_per_100g: float | None


class FoodSuggestion(FoodSearchHit):
    name: str                                   # "Greek yogurt" for listed foods, the USDA description otherwise
    data_type: str | None
    source: Literal["list", "usda"]


class MealItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meal_item_id: UUID
    ingredient_text: str
    food: FoodRef | None
    quantity: float
    unit: str | None
    grams: float | None
    portion_label: str | None
    is_assumed: bool
    needs_review: bool
    match_confidence: float | None
    source_dish: str | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    alternatives: list[FoodSearchHit]
    unit_options: list[str]


class MealOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    meal_id: UUID
    user_id: UUID
    log_date: date
    meal_type: str | None
    raw_text: str | None
    display_name: str | None
    status: str
    totals: dict[str, float]
    items: list[MealItemOut]
