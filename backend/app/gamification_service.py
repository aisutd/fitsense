"""Transactional point, FitCoin, badge and streak helpers used by log endpoints."""

from datetime import date, timedelta

from app.gamification import BADGE_REWARDS, FITCOINS, LEVEL_THRESHOLDS, POINTS, PointAction


def award_action(db, user_id: str, action: PointAction, source_id: str | None = None) -> dict:
    """Award XP and FitCoins once per source, then unlock any earned badges."""
    result = db.rpc("award_points", {
        "p_user_id": user_id,
        "p_action": action.value,
        "p_points": POINTS[action],
        "p_level_thresholds": LEVEL_THRESHOLDS,
        "p_source_id": source_id,
    }).execute().data[0]
    awarded = bool(result["awarded"])
    badge_names = []
    badge_coins = 0

    if awarded and action == PointAction.workout_completed:
        completed = db.table("workout_logs").select("workout_log_id").eq(
            "user_id", user_id
        ).eq("completion_status", "completed").limit(1000).execute().data
        count = len(completed)
        badge_names.extend(
            name for name, spec in BADGE_REWARDS.items()
            if spec["threshold"] is not None and count >= spec["threshold"]
        )
    if awarded and action == PointAction.streak_7_days:
        badge_names.append("seven_day_streak")

    new_badges = []
    for name in dict.fromkeys(badge_names):
        badge = db.table("badges").select("badge_id").eq("name", name).limit(1).execute().data
        if not badge:
            continue
        fitcoins = BADGE_REWARDS[name]["fitcoins"]
        unlocked = db.rpc("award_badge_coins", {
            "p_user_id": user_id,
            "p_badge_id": badge[0]["badge_id"],
            "p_fitcoins": fitcoins,
        }).execute().data[0]
        if unlocked["awarded"]:
            new_badges.append({"id": name, "fitcoins": fitcoins})
            badge_coins += fitcoins

    game = db.table("user_gamification").select("fitcoins").eq("user_id", user_id).limit(1).execute().data
    return {
        "action": action.value,
        "awarded": awarded,
        "points_awarded": POINTS[action] if awarded else 0,
        "fitcoins_awarded": (FITCOINS[action] if awarded else 0) + badge_coins,
        "fitcoins_balance": (game[0].get("fitcoins") or 0) if game else 0,
        "badges_earned": new_badges,
        "total_points": result["new_total_xp"],
        "level": result["new_level"],
        "previous_level": result["previous_level"],
    }


def record_workout_streak(db, user_id: str, workout_day: date) -> dict | None:
    """Update consecutive completed-workout days and grant a streak award each 7 days."""
    rows = db.table("workout_logs").select("workout_date").eq(
        "user_id", user_id
    ).eq("completion_status", "completed").lte(
        "workout_date", workout_day.isoformat()
    ).order("workout_date", desc=True).limit(60).execute().data
    days = {date.fromisoformat(str(row["workout_date"])[:10]) for row in rows}
    if workout_day not in days:
        return None

    streak = 1
    cursor = workout_day - timedelta(days=1)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)

    previous = db.table("user_streaks").select("current_streak, longest_streak, last_completed_date").eq(
        "user_id", user_id
    ).eq("streak_type", "workout").limit(1).execute().data
    if previous and previous[0].get("last_completed_date"):
        last_day = date.fromisoformat(str(previous[0]["last_completed_date"])[:10])
        if workout_day < last_day:
            return None

    db.table("user_streaks").upsert({
        "user_id": user_id,
        "streak_type": "workout",
        "current_streak": streak,
        "longest_streak": max(streak, previous[0].get("longest_streak", 0) if previous else 0),
        "last_completed_date": workout_day.isoformat(),
    }, on_conflict="user_id,streak_type").execute()

    reward = None
    if streak >= 7 and streak % 7 == 0:
        reward = award_action(db, user_id, PointAction.streak_7_days, workout_day.isoformat())
    return {"current_streak": streak, "longest_streak": max(streak, previous[0].get("longest_streak", 0) if previous else 0), "reward": reward}
