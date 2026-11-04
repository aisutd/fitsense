from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app import healthscore_repo as repo
from app import plans
from app.database import get_supabase
from app.gamification import PointAction
from app.gamification_service import award_action, checkin, record_workout_streak
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


@router.get("/logs/{user_id}/day/{log_date}")
def get_day(user_id: UUID, log_date: date, supabase: Client = Depends(get_supabase)):
    """Everything logged for one day: workouts, steps, confirmed meals, and the night of sleep
    before it (the one the daily HealthScore uses)."""
    uid, day = str(user_id), log_date.isoformat()
    night = (log_date - timedelta(days=1)).isoformat()
    try:
        repo.get_profile(supabase, uid)
        workouts = (supabase.table("workout_logs").select("workout_log_id, completion_status, duration_minutes")
                    .eq("user_id", uid).eq("workout_date", day).execute().data)
        sleep = (supabase.table("sleep_logs").select("sleep_date, hours_slept, sleep_quality")
                 .eq("user_id", uid).eq("sleep_date", night).limit(1).execute().data)
        activity = (supabase.table("activity_logs").select("steps, active_minutes, calories_burned")
                    .eq("user_id", uid).eq("log_date", day).limit(1).execute().data)
        meals = (supabase.table("meal_entries").select("meal_id, meal_type, display_name, calories, protein_g, carbs_g, fat_g, created_at")
                 .eq("user_id", uid).eq("log_date", day).eq("status", "confirmed").order("created_at").execute().data)
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to load the day: {e.message}")
    return {"date": day, "workouts": workouts, "sleep": sleep[0] if sleep else None,
            "activity": activity[0] if activity else None, "meals": meals}


@router.post("/logs/{user_id}/workouts")
def log_workout(user_id: UUID, body: WorkoutLogIn, supabase: Client = Depends(get_supabase)):
    """Record a workout (completed, partial or skipped)."""
    row = {"user_id": str(user_id), **body.model_dump(mode="json")}
    if body.plan_id is None:
        # count it toward that week's workout plan (its next open day), so the plan can adapt
        try:
            linked = plans.plan_day_for(supabase, str(user_id), body.workout_date)
        except APIError:
            linked = None
        if linked:
            row["plan_id"], row["day_number"] = linked
    saved = _write("log workout", lambda: supabase.table("workout_logs").insert(row).execute())
    reward = None
    streak = None
    if body.completion_status.value == "completed":
        reward = award_action(supabase, str(user_id), PointAction.workout_completed, saved["workout_log_id"])
        streak = record_workout_streak(supabase, str(user_id), body.workout_date)
    elif body.completion_status.value == "partial":
        reward = award_action(supabase, str(user_id), PointAction.workout_partial, saved["workout_log_id"])
    reward, days = checkin(supabase, str(user_id), body.workout_date, reward)
    return {**saved, "rewards": reward, "streak": streak, "checkin_streak": days}


@router.put("/logs/{user_id}/sleep/{sleep_date}")
def log_sleep(user_id: UUID, sleep_date: date, body: SleepLogIn, supabase: Client = Depends(get_supabase)):
    """Record (or replace) the sleep for the night starting on sleep_date."""
    row = {"user_id": str(user_id), "sleep_date": sleep_date.isoformat(), **body.model_dump(mode="json")}
    saved = _write("log sleep", lambda: supabase.table("sleep_logs").upsert(row, on_conflict="user_id,sleep_date").execute())
    reward = award_action(supabase, str(user_id), PointAction.sleep_logged, sleep_date.isoformat())
    reward, days = checkin(supabase, str(user_id), sleep_date + timedelta(days=1), reward)
    return {**saved, "rewards": reward, "checkin_streak": days}


@router.put("/logs/{user_id}/activity/{log_date}")
def log_activity(user_id: UUID, log_date: date, body: ActivityLogIn, supabase: Client = Depends(get_supabase)):
    """Record (or replace) a day's steps and/or active minutes."""
    row = {"user_id": str(user_id), "log_date": log_date.isoformat(), **body.model_dump(mode="json")}
    saved = _write("log activity", lambda: supabase.table("activity_logs").upsert(row, on_conflict="user_id,log_date").execute())
    profile = repo.get_profile(supabase, str(user_id))
    targets = repo.current_goals(supabase, str(user_id), profile)
    met_steps = body.steps is not None and body.steps >= targets["daily_steps"]
    met_minutes = body.active_minutes is not None and body.active_minutes >= targets["daily_active_minutes"]
    reward = award_action(supabase, str(user_id), PointAction.daily_goals_met, log_date.isoformat()) if (met_steps or met_minutes) else None
    reward, days = checkin(supabase, str(user_id), log_date, reward)
    return {**saved, "rewards": reward, "checkin_streak": days}


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
    saved = _write("log meal", lambda: supabase.table("meal_entries").insert(row).execute())
    reward = award_action(supabase, str(user_id), PointAction.meal_logged, saved["meal_id"])
    reward, days = checkin(supabase, str(user_id), body.log_date, reward)
    return {**saved, "rewards": reward, "checkin_streak": days}


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
