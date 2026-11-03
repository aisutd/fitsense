from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app import plans
from app.database import get_supabase

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
