from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app import plans
from app.database import get_supabase
from app.schemas import PlanSwapIn

router = APIRouter(prefix="/plans", tags=["workout plans"])


@router.get("/{user_id}/current")
def get_current_plan(
    user_id: UUID,
    today: date | None = Query(default=None, description="The player's local date; picks the week. Defaults to the server's today."),
    supabase: Client = Depends(get_supabase),
):
    """This week's workout plan, built (and saved) on first view from the profile and last week's plan.

    Log a plan day with POST /logs/{user_id}/workouts and its plan_id + day_number: next week's plan
    adapts to how many plan days were completed."""
    try:
        return plans.current_plan(supabase, str(user_id), today or date.today())
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to load the workout plan: {e.message}")


@router.post("/{user_id}/swap")
def swap_plan_day(
    user_id: UUID,
    body: PlanSwapIn,
    today: date | None = Query(default=None, description="The player's local date; picks the week."),
    supabase: Client = Depends(get_supabase),
):
    """Swap today's exercises when something's different: no barbell, training at home or outdoors,
    or an exercise the player can't do. The closest allowed exercise replaces each one, keeping the
    sets and reps already reached. Only this week's plan changes, not the profile.

    Log the day afterwards with swapped=true (or skipped + skip_reason=no_equipment instead), so
    next week's plan doesn't count it as a missed workout."""
    conditions = {"location": body.location.value if body.location else None,
                  "equipment": [e.strip().lower() for e in body.equipment] if body.equipment is not None else None,
                  "without": [e.strip().lower() for e in body.without]}
    try:
        return plans.swap_day(supabase, str(user_id), today or date.today(), body.day, conditions,
                              body.exercises, body.rest_of_week)
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to swap exercises: {e.message}")
