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


# Where each kind of log says which day it was for. Sleep is logged for the night before, so last
# night's sleep is a check-in for the day you woke up.
CHECKIN_DATES = (("workout_logs", "workout_date", 0), ("activity_logs", "log_date", 0),
                 ("meal_entries", "log_date", 0), ("sleep_logs", "sleep_date", 1))
CHECKIN_LOOKBACK = 120


def checkin_streak(db, user_id: str, day: date) -> int:
    """Consecutive days, ending on day, with anything logged: a workout, steps, sleep or a confirmed meal.

    Unlike the workout streak this one survives recovery days, so it drives the reward effects."""
    start = day - timedelta(days=CHECKIN_LOOKBACK)
    days = set()
    for table, column, shift in CHECKIN_DATES:
        query = (db.table(table).select(column).eq("user_id", user_id)
                 .gte(column, (start - timedelta(days=shift)).isoformat())
                 .lte(column, (day - timedelta(days=shift)).isoformat()))
        if table == "meal_entries":
            query = query.eq("status", "confirmed")
        days |= {date.fromisoformat(str(row[column])[:10]) + timedelta(days=shift) for row in query.execute().data}
    streak = 0
    while day - timedelta(days=streak) in days:
        streak += 1
    return streak


def merge_rewards(reward: dict | None, extra: dict | None) -> dict | None:
    """One reward for a log that earned several (the log itself plus a streak bonus)."""
    if not extra or not extra.get("awarded"):
        return reward
    if not reward:
        return extra
    return {**reward,
            "points_awarded": reward["points_awarded"] + extra["points_awarded"],
            "fitcoins_awarded": reward["fitcoins_awarded"] + extra["fitcoins_awarded"],
            "fitcoins_balance": extra["fitcoins_balance"],
            "badges_earned": reward["badges_earned"] + extra["badges_earned"],
            "total_points": extra["total_points"], "level": extra["level"]}


def checkin(db, user_id: str, day: date, reward: dict | None) -> tuple[dict | None, int]:
    """(reward, check-in streak) after a log for day: every 7th day in a row adds the 7-day streak
    reward and badge. Recovery days count as long as something was logged."""
    streak = checkin_streak(db, user_id, day)
    if streak >= 7 and streak % 7 == 0:
        bonus = award_action(db, user_id, PointAction.streak_7_days, f"checkin:{day.isoformat()}")
        reward = merge_rewards(reward, bonus)
    return reward, streak


def record_workout_streak(db, user_id: str, workout_day: date) -> dict | None:
    """Update consecutive completed-workout days (shown in the dashboard). The 7-day streak reward
    comes from the check-in streak instead (checkin()), which recovery days don't break."""
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

    return {"current_streak": streak, "longest_streak": max(streak, previous[0].get("longest_streak", 0) if previous else 0)}
