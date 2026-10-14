from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase
from app.gamification import LEVEL_THRESHOLDS, POINTS, level_progress
from app.schemas import (
    AwardPointsIn,
    AwardPointsOut,
    LevelInfo,
    PointActionInfo,
    PointEvent,
    PointsStatus,
)

router = APIRouter(prefix="/gamification", tags=["gamification"])

FK_VIOLATION = "23503"


def _status(user_id: UUID, total: int) -> dict:
    return {"user_id": user_id, "total_points": total, **level_progress(total)}


def _profile_exists(supabase: Client, user_id: UUID) -> bool:
    response = (
        supabase.table("profiles").select("user_id").eq("user_id", str(user_id)).limit(1).execute()
    )
    return bool(response.data)


@router.get("/actions", response_model=list[PointActionInfo])
def list_actions():
    """Actions that earn points and how many each is worth."""
    return [{"action": action, "points": points} for action, points in POINTS.items()]


@router.get("/levels", response_model=list[LevelInfo])
def list_levels():
    """Minimum points needed for each level."""
    return [{"level": i + 1, "min_points": p} for i, p in enumerate(LEVEL_THRESHOLDS)]


@router.get("/{user_id}", response_model=PointsStatus)
def get_points(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """A user's total points and level. Users with no points yet are at 0 / level 1."""
    try:
        response = (
            supabase.table("user_gamification")
            .select("total_xp")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        if response.data:
            return _status(user_id, response.data[0]["total_xp"])
        if not _profile_exists(supabase, user_id):
            raise HTTPException(status_code=404, detail="Profile not found")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch points: {e.message}")
    return _status(user_id, 0)


@router.post("/{user_id}/points", response_model=AwardPointsOut)
def award_points(user_id: UUID, body: AwardPointsIn, supabase: Client = Depends(get_supabase)):
    """Add points to a user for completing an action."""
    points = POINTS[body.action]
    try:
        response = supabase.rpc(
            "award_points",
            {
                "p_user_id": str(user_id),
                "p_action": body.action.value,
                "p_points": points,
                "p_level_thresholds": LEVEL_THRESHOLDS,
                "p_source_id": body.source_id,
            },
        ).execute()
    except APIError as e:
        if e.code == FK_VIOLATION:
            raise HTTPException(status_code=404, detail="Profile not found")
        raise HTTPException(status_code=502, detail=f"Failed to award points: {e.message}")
    if not response.data:
        raise HTTPException(status_code=502, detail="Failed to award points: no data returned")

    result = response.data[0]
    status = _status(user_id, result["new_total_xp"])
    return {
        **status,
        "action": body.action,
        "points_awarded": points if result["awarded"] else 0,
        "awarded": result["awarded"],
        "previous_level": result["previous_level"],
        "leveled_up": status["level"] > result["previous_level"],
    }


@router.get("/{user_id}/history", response_model=list[PointEvent])
def get_history(
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    supabase: Client = Depends(get_supabase),
):
    """Most recent point awards for a user, newest first."""
    try:
        response = (
            supabase.table("xp_events")
            .select("event_id, action, points, source_id, created_at")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch history: {e.message}")
    return response.data
