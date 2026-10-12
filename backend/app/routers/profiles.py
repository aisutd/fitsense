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
    try:
        response = supabase.table(TABLE).upsert(row, on_conflict="user_id").execute()
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
