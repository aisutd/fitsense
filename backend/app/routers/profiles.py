from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase
from app.schemas import ProfileIn, ProfileOut

router = APIRouter(prefix="/profiles", tags=["profiles"])

TABLE = "profiles"


@router.put("/{user_id}", response_model=ProfileOut)
def save_profile(user_id: UUID, profile: ProfileIn, supabase: Client = Depends(get_supabase)):
    """Create or replace the onboarding profile for a user."""
    row = {"user_id": str(user_id), **profile.model_dump(mode="json")}
    # Workout fields also live in user_preferences (data model); keep them in sync
    # until the profile columns are retired. available_equipment is left untouched.
    preferences = {
        "user_id": row["user_id"],
        "workout_days_per_week": row["workout_frequency"],
        "workout_location": row["workout_location"],
        "preferred_workout_types": row["workout_preferences"],
    }
    try:
        response = supabase.table(TABLE).upsert(row, on_conflict="user_id").execute()
        supabase.table("user_preferences").upsert(preferences, on_conflict="user_id").execute()
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to save profile: {e.message}")
    if not response.data:
        raise HTTPException(status_code=502, detail="Failed to save profile: no data returned")
    return response.data[0]


@router.get("/{user_id}", response_model=ProfileOut)
def get_profile(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """Fetch the onboarding profile for a user."""
    try:
        response = (
            supabase.table(TABLE)
            .select("*")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch profile: {e.message}")
    if not response.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return response.data[0]
