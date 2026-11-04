from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app import forecast
from app.database import get_supabase

router = APIRouter(prefix="/forecast", tags=["forecast"])

DISCLAIMER = ("Forecasts extend recent weekly trends and are rough with only a few weeks of data. "
              "HealthScore is an experimental motivational wellness metric, not a medical assessment.")


@router.get("/{user_id}/healthscore")
def healthscore_forecast(
    user_id: UUID,
    end_date: date | None = Query(default=None, description="The user's local today. Defaults to the server's today."),
    supabase: Client = Depends(get_supabase),
):
    """Where the HealthScore is heading (1, 4 and 12 weeks), and how many workouts a week change it."""
    try:
        result = forecast.healthscore_forecast(supabase, str(user_id), end_date or date.today())
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to forecast HealthScore: {e.message}")
    return {**result, "disclaimer": DISCLAIMER}
