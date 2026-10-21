
from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.database import get_supabase
from app.leaderboard import rank_users

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("")
def get_leaderboard(supabase: Client = Depends(get_supabase)):
    """Return users ranked by lifetime XP."""
    try:
        response = (
            supabase.table("user_gamification")
            .select("user_id, total_xp, level")
            .execute()
        )
    except APIError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch leaderboard: {e.message}",
        )

    return rank_users(response.data)
