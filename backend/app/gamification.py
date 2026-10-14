"""Point values and level thresholds for FitSense gamification.

This is the single source of truth: the backend passes these values to the
award_points() database function (backend/sql/003_gamification_points.sql).
"""

from bisect import bisect_right
from enum import Enum


class PointAction(str, Enum):
    onboarding_completed = "onboarding_completed"
    workout_completed = "workout_completed"
    workout_partial = "workout_partial"
    meal_logged = "meal_logged"
    sleep_logged = "sleep_logged"
    daily_goals_met = "daily_goals_met"
    streak_7_days = "streak_7_days"


POINTS: dict[PointAction, int] = {
    PointAction.onboarding_completed: 100,
    PointAction.workout_completed: 50,
    PointAction.workout_partial: 20,
    PointAction.meal_logged: 10,
    PointAction.sleep_logged: 10,
    PointAction.daily_goals_met: 25,
    PointAction.streak_7_days: 100,
}

# Minimum points for each level: index 0 = level 1. Must start at 0 and ascend.
LEVEL_THRESHOLDS: list[int] = [0, 200, 500, 1000, 1750, 2750, 4000, 5500, 7500, 10000]
MAX_LEVEL = len(LEVEL_THRESHOLDS)


def level_for(points: int) -> int:
    """Level reached with the given total points (minimum 1)."""
    return max(1, bisect_right(LEVEL_THRESHOLDS, max(points, 0)))


def level_progress(points: int) -> dict:
    """Level plus where the user sits between this level and the next."""
    level = level_for(points)
    current_min = LEVEL_THRESHOLDS[level - 1]
    if level == MAX_LEVEL:
        return {
            "level": level,
            "current_level_points": current_min,
            "next_level_points": None,
            "points_to_next_level": None,
            "progress_percent": 100.0,
        }
    next_min = LEVEL_THRESHOLDS[level]
    return {
        "level": level,
        "current_level_points": current_min,
        "next_level_points": next_min,
        "points_to_next_level": next_min - points,
        "progress_percent": round((points - current_min) / (next_min - current_min) * 100, 1),
    }
