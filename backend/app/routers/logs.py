from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app import healthscore_repo as repo
from app.database import get_supabase
from app.schemas import ActivityLogIn, GoalsIn, GoalsOut, MealLogIn, SleepLogIn, WorkoutLogIn

router = APIRouter(tags=["logs & goals"])

FK_VIOLATION = "23503"


def _write(action: str, run):
    """Run a Supabase write, mapping a missing profile to 404 and other errors to 502."""
    try:
        response = run()
    except APIError as e:
        if e.code == FK_VIOLATION:
            raise HTTPException(status_code=404, detail="Profile not found")
        raise HTTPException(status_code=502, detail=f"Failed to {action}: {e.message}")
    return response.data[0] if response.data else None


@router.post("/logs/{user_id}/workouts")
def log_workout(user_id: UUID, body: WorkoutLogIn, supabase: Client = Depends(get_supabase)):
    """Record a workout (completed, partial or skipped)."""
    row = {"user_id": str(user_id), **body.model_dump(mode="json")}
    return _write("log workout", lambda: supabase.table("workout_logs").insert(row).execute())


@router.put("/logs/{user_id}/sleep/{sleep_date}")
def log_sleep(user_id: UUID, sleep_date: date, body: SleepLogIn, supabase: Client = Depends(get_supabase)):
    """Record (or replace) the sleep for the night starting on sleep_date."""
    row = {"user_id": str(user_id), "sleep_date": sleep_date.isoformat(), **body.model_dump(mode="json")}
    return _write("log sleep", lambda: supabase.table("sleep_logs").upsert(row, on_conflict="user_id,sleep_date").execute())


@router.put("/logs/{user_id}/activity/{log_date}")
def log_activity(user_id: UUID, log_date: date, body: ActivityLogIn, supabase: Client = Depends(get_supabase)):
    """Record (or replace) a day's steps and/or active minutes."""
    row = {"user_id": str(user_id), "log_date": log_date.isoformat(), **body.model_dump(mode="json")}
    return _write("log activity", lambda: supabase.table("activity_logs").upsert(row, on_conflict="user_id,log_date").execute())


@router.post("/logs/{user_id}/meals")
def log_meal(user_id: UUID, body: MealLogIn, supabase: Client = Depends(get_supabase)):
    """Store a confirmed meal from the NLP + FoodData Central pipeline.

    The nutrition values feed the HealthScore's nutrition category.
    """
    row = {
        "user_id": str(user_id),
        **body.model_dump(mode="json"),
        "status": "confirmed",
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    return _write("log meal", lambda: supabase.table("meal_entries").insert(row).execute())


@router.get("/goals/{user_id}", response_model=GoalsOut)
def get_goals(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """Current targets used by the HealthScore (defaults or estimates where none are set)."""
    try:
        profile = repo.get_profile(supabase, str(user_id))
        return repo.current_goals(supabase, str(user_id), profile)
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch goals: {e.message}")


@router.put("/goals/{user_id}", response_model=GoalsOut)
def set_goals(user_id: UUID, body: GoalsIn, supabase: Client = Depends(get_supabase)):
    """Set any of the user's targets. Goal tables keep history; the newest row is the current target."""
    uid = str(user_id)
    try:
        profile = repo.get_profile(supabase, uid)
        if body.nutrition:
            supabase.table("nutrition_goals").insert({"user_id": uid, **body.nutrition.model_dump(mode="json")}).execute()
        if body.sleep_target_hours is not None:
            supabase.table("sleep_goals").insert({"user_id": uid, "target_hours": body.sleep_target_hours}).execute()
        for goal_type in ("daily_steps", "daily_active_minutes"):
            value = getattr(body, goal_type)
            if value is not None:
                supabase.table("progress_goals").insert(
                    {"user_id": uid, "goal_type": goal_type, "target_value": value, "status": "active"}
                ).execute()
        return repo.current_goals(supabase, uid, profile)
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to save goals: {e.message}")
