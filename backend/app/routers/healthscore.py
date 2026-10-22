from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app import healthscore_repo as repo
from app.database import get_supabase
from app.schemas import HealthScoreHistoryItem, HealthScoreOut, HealthScoreRange, HealthScoreSnapshotOut

router = APIRouter(prefix="/healthscore", tags=["healthscore"])

DISCLAIMER = "HealthScore is an experimental motivational wellness metric, not a medical assessment."


def _calculate(supabase: Client, user_id: UUID, range_key: HealthScoreRange, end_date: date | None):
    try:
        result, config_id = repo.calculate(supabase, str(user_id), range_key.value, end_date or date.today())
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to calculate HealthScore: {e.message}")
    return {"user_id": user_id, **result, "disclaimer": DISCLAIMER}, config_id


@router.get("/{user_id}", response_model=HealthScoreOut)
def get_healthscore(
    user_id: UUID,
    range: HealthScoreRange = HealthScoreRange.week,
    end_date: date | None = Query(default=None, description="Last day of the window (the user's local today). Defaults to the server's today."),
    supabase: Client = Depends(get_supabase),
):
    """Calculate the HealthScore for a window without saving it."""
    result, _ = _calculate(supabase, user_id, range, end_date)
    return result


@router.post("/{user_id}/snapshots", response_model=HealthScoreSnapshotOut)
def save_snapshot(
    user_id: UUID,
    range: HealthScoreRange = HealthScoreRange.week,
    end_date: date | None = None,
    supabase: Client = Depends(get_supabase),
):
    """Calculate the HealthScore and store it in health_scores (history for trends and forecasting)."""
    result, config_id = _calculate(supabase, user_id, range, end_date)
    row = {
        "user_id": str(user_id),
        "score": result["overall_score"],
        "workout_score": result["workouts"],
        "nutrition_score": result["nutrition"],
        "sleep_score": result["sleep"],
        "activity_score": result["activity"],
        "provisional": result["provisional"],
        "range_start": result["range"]["start"].isoformat(),
        "range_end": result["range"]["end"].isoformat(),
        "config_id": config_id,
    }
    try:
        saved = supabase.table("health_scores").insert(row).execute().data[0]
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to save HealthScore: {e.message}")
    return {**result, "score_id": saved["score_id"], "calculated_at": saved["calculated_at"]}


@router.get("/{user_id}/history", response_model=list[HealthScoreHistoryItem])
def get_history(
    user_id: UUID,
    limit: int = Query(default=30, ge=1, le=365),
    supabase: Client = Depends(get_supabase),
):
    """Saved HealthScore snapshots, newest first."""
    try:
        response = (
            supabase.table("health_scores").select("*").eq("user_id", str(user_id))
            .order("calculated_at", desc=True).limit(limit).execute()
        )
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch HealthScore history: {e.message}")
    return response.data
