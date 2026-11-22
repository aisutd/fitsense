from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app import achievement_service
from app.achievements import BY_CODE
from app.cache import per_client
from app.concurrency import parallel
from app.database import get_supabase
from app.gamification import AVATARS, LEAGUES, LEVEL_THRESHOLDS, POINTS, PointAction, level_progress
from app.gamification_service import award_action, checkin_days, streak_ending
from app import healthscore_repo as health_repo
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


def _status(user_id: UUID, total: int, fitcoins: int = 0, equipped_avatar: str = "starter") -> dict:
    return {
        "user_id": user_id, "total_points": total, "fitcoins": fitcoins,
        "equipped_avatar": equipped_avatar, **level_progress(total),
    }


def _profile_exists(supabase: Client, user_id: UUID) -> bool:
    response = (
        supabase.table("profiles").select("user_id").eq("user_id", str(user_id)).limit(1).execute()
    )
    return bool(response.data)


SEASON_WEEKS = 4
SEASON_DAYS = SEASON_WEEKS * 7
SEASON_ANCHOR = date(2026, 10, 26)  # Monday; seasons roll over every four weeks.


def _season_start(today: date) -> date:
    if today < SEASON_ANCHOR:
        return SEASON_ANCHOR
    return SEASON_ANCHOR + timedelta(days=((today - SEASON_ANCHOR).days // SEASON_DAYS) * SEASON_DAYS)


STANDINGS_TTL = timedelta(minutes=10)   # league standings are recomputed at most this often
UPSERT_CHUNK = 500
LOOKUP_CHUNK = 100   # user ids per in_() lookup
PROMOTION_SHARE = 0.2   # top and bottom fifth of a league move up / down when the season closes
MIN_MOVING_LEAGUE = 5   # smaller leagues hold their tiers
CATALOG_TTL = 300   # seconds the badge list is reused for
SEASON_SETUP_TTL = 600   # seconds: how often the season bookkeeping is re-run (it's idempotent)


def _active_days(logs: dict) -> int:
    """Days in the season with any check-in: a completed workout, steps, sleep or a confirmed meal."""
    days = {str(r["workout_date"])[:10] for r in logs["workout_logs"] if r["completion_status"] == "completed"}
    days |= {str(r["log_date"])[:10] for r in logs["activity_logs"]}
    days |= {str(r["sleep_date"])[:10] for r in logs["sleep_logs"]}
    days |= {str(r["log_date"])[:10] for r in logs["meal_entries"]}
    return len(days)


def _private_score(health_score: float, active_days: int, elapsed_days: int) -> float:
    """Ranking score: season HealthScore plus habit consistency. The weighting isn't shown to players."""
    return 0.75 * float(health_score) + 25.0 * min(1.0, active_days / max(1, elapsed_days))


def _age(rows: list[dict]) -> timedelta:
    """How old a season's standings are, from their rows' updated_at."""
    newest = max(str(row["updated_at"]) for row in rows)
    return datetime.now(timezone.utc) - datetime.fromisoformat(newest.replace("Z", "+00:00"))


def _refresh_standings(supabase: Client, season_start: date, season_end: date, today: date) -> None:
    """Score every player for the season so far (a few bulk queries) and store the standings.

    Everyone with a season HealthScore is in their tier's league, whether or not they have
    opened the league page."""
    now = datetime.now(timezone.utc)
    end = min(today, season_end)
    elapsed = (end - season_start).days + 1
    scores = health_repo.calculate_everyone(supabase, season_start, end)
    tiers = {r["user_id"]: r.get("league_tier") or 0
             for r in health_repo.all_rows(lambda: supabase.table("user_gamification").select("user_id, league_tier").order("user_id"))}
    rows = [{
        "season_start": season_start.isoformat(), "user_id": uid, "tier": tiers.get(uid, 0),
        "hidden_score": round(_private_score(result["overall_score"], _active_days(result["logs"]), elapsed), 3),
        "health_score": result["overall_score"], "active_days": _active_days(result["logs"]),
        "updated_at": now.isoformat(),
    } for uid, result in scores.items() if result["overall_score"] is not None]
    for i in range(0, len(rows), UPSERT_CHUNK):
        supabase.table("league_season_scores").upsert(rows[i:i + UPSERT_CHUNK], on_conflict="season_start,user_id").execute()


def _ensure_game_row(supabase: Client, user_id: str) -> dict:
    rows = supabase.table("user_gamification").select("*").eq("user_id", user_id).limit(1).execute().data
    if not rows:
        if not _profile_exists(supabase, UUID(user_id)):
            raise HTTPException(status_code=404, detail="Profile not found")
        supabase.table("user_gamification").insert({"user_id": user_id}).execute()
        rows = supabase.table("user_gamification").select("*").eq("user_id", user_id).limit(1).execute().data
    return rows[0]


def _display_name(profile: dict | None, account: dict | None, user_id: str) -> str:
    return (profile or {}).get("name") or (account or {}).get("username") or f"Player {user_id[:4]}"


def _names_and_avatars(supabase: Client, ids: list[str]) -> dict[str, tuple[str, str, str | None, str]]:
    """{user_id: (display name, equipped avatar, fitness level, avatar body)}, looked up in batches."""
    tables = [("profiles", "user_id, name, fitness_level"), ("accounts", "user_id, username"),
              ("user_gamification", "user_id, equipped_avatar, avatar_body")]
    batches = [ids[i:i + LOOKUP_CHUNK] for i in range(0, len(ids), LOOKUP_CHUNK)]
    # every batch of every table at once
    reads = parallel(*[lambda t=table, c=columns, b=batch: supabase.table(t).select(c).in_("user_id", b).execute().data
                       for table, columns in tables for batch in batches])
    found = [dict() for _ in tables]
    for n, rows in enumerate(reads):
        found[n // max(1, len(batches))] |= {r["user_id"]: r for r in rows}
    profiles, accounts, games = found
    return {u: (_display_name(profiles.get(u), accounts.get(u), u), (games.get(u) or {}).get("equipped_avatar") or "starter",
                (profiles.get(u) or {}).get("fitness_level"), (games.get(u) or {}).get("avatar_body") or "male")
            for u in ids}


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
            .select("total_xp, fitcoins, equipped_avatar")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        if response.data:
            row = response.data[0]
            return _status(user_id, row["total_xp"], row.get("fitcoins") or 0, row.get("equipped_avatar") or "starter")
        if not _profile_exists(supabase, user_id):
            raise HTTPException(status_code=404, detail="Profile not found")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch points: {e.message}")
    return _status(user_id, 0)


@router.get("/{user_id}/league")
def get_league(user_id: UUID, background: BackgroundTasks, supabase: Client = Depends(get_supabase)):
    """Return a four-week league board; the ranking score stays server-side."""
    uid = str(user_id)
    today = datetime.now(timezone.utc).date()
    season_start = _season_start(today)
    season_end = season_start + timedelta(days=SEASON_DAYS - 1)
    previous_start = season_start - timedelta(days=SEASON_DAYS)
    try:
        # closing last season and recording this one only needs doing once a season, not on every view
        def open_season():
            supabase.rpc("finalize_league_season", {"p_season_start": previous_start.isoformat()}).execute()
            supabase.table("league_seasons").upsert(
                {"season_start": season_start.isoformat(), "season_end": season_end.isoformat()},
                on_conflict="season_start",
            ).execute()
            return True
        per_client(supabase, f"league-season:{season_start}", SEASON_SETUP_TTL, open_season)
        # the whole season's standings (every league; a few hundred rows) in one read, with your game row
        # and last season's tier, all at once
        def season_rows():
            return health_repo.all_rows(lambda: supabase.table("league_season_scores")
                                        .select("user_id, tier, hidden_score, health_score, updated_at")
                                        .eq("season_start", season_start.isoformat()).order("hidden_score", desc=True))
        game, everyone, before = parallel(
            lambda: _ensure_game_row(supabase, uid),
            season_rows,
            lambda: (supabase.table("league_season_scores").select("tier").eq("season_start", previous_start.isoformat())
                     .eq("user_id", uid).limit(1).execute().data),
        )
        if not everyone:
            _refresh_standings(supabase, season_start, season_end, today)        # first view of the season
            everyone = season_rows()
        elif _age(everyone) > STANDINGS_TTL:
            # answer from the current standings; recompute after the response is sent
            background.add_task(_refresh_standings, supabase, season_start, season_end, today)

        tier = int(game.get("league_tier") or 0)
        rows = [row for row in everyone if int(row.get("tier") or 0) == tier]   # already best first
        members = len(rows)
        position = next((i + 1 for i, row in enumerate(rows) if row["user_id"] == uid), None)
        mine = rows[position - 1] if position else None
        moving = max(1, ceil(members * PROMOTION_SHARE)) if members >= MIN_MOVING_LEAGUE else 0

        def zone(place: int) -> str | None:
            if moving and tier < len(LEAGUES) - 1 and place <= moving:
                return "promotion"
            if moving and tier > 0 and place > members - moving:
                return "demotion"
            return None

        movement = "needs a HealthScore"
        if position is not None:
            movement = ("building a league" if not moving else
                        {"promotion": "promotion zone", "demotion": "demotion zone"}.get(zone(position), "holding position"))

        # The whole league, by place: names, avatars and fitness levels only; the ranking score stays server-side.
        ids = [row["user_id"] for row in rows]
        names, unlocked = parallel(
            lambda: _names_and_avatars(supabase, list(dict.fromkeys([*ids, uid]))),   # plus you, for the banner
            lambda: achievement_service.evaluate(supabase, uid, "league", today, {
                "tier": tier, "league": LEAGUES[tier], "position": position, "members": members,
                "previous_tier": int(before[0]["tier"]) if before else None,
            }),
        )
        standings = [{"place": i + 1, "name": names[u][0], "avatar_id": names[u][1], "fitness_level": names[u][2],
                      "avatar_body": names[u][3], "is_current_user": u == uid, "zone": zone(i + 1)} for i, u in enumerate(ids)]
        podium = [{**row, "user_id": ids[row["place"] - 1]} for row in standings[:5]]
        return {
            "season": {
                "start": season_start.isoformat(), "end": season_end.isoformat(),
                "week": min(SEASON_WEEKS, max(1, (today - season_start).days // 7 + 1)),
                "weeks": SEASON_WEEKS,
            },
            "league": {
                "tier": tier, "name": LEAGUES[tier], "position": position,
                "members": members, "movement": movement,
                # shown on the banner as the league score; the ranking score itself stays private
                "season_health_score": round(float(mine["health_score"])) if mine and mine.get("health_score") is not None else None,
            },
            "player": {
                "name": names[uid][0],
                "fitness_level": names[uid][2],
                "avatar_body": game.get("avatar_body") or "male",   # column from backend/sql/010
                "equipped_avatar": game.get("equipped_avatar") or "starter",   # the outfit from the shop
            },
            "podium": podium,
            "standings": standings,
            "leagues": LEAGUES,
            "promotion_share": PROMOTION_SHARE,
            "achievements": unlocked,
        }
    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to load league: {e.message}")


@router.get("/{user_id}/avatars")
def get_avatars(user_id: UUID, supabase: Client = Depends(get_supabase)):
    uid = str(user_id)
    try:
        today = datetime.now(timezone.utc).date()
        # independent reads, all at once (the badge list hardly changes, so it's cached briefly)
        game, owned_rows, earned, badge_catalog, streaks, checkins = parallel(
            lambda: _ensure_game_row(supabase, uid),
            lambda: supabase.table("user_avatars").select("avatar_id").eq("user_id", uid).execute().data,
            lambda: supabase.table("user_badges").select("badge_id, earned_at").eq("user_id", uid).execute().data,
            lambda: per_client(supabase, "badges", CATALOG_TTL, lambda: {
                row["badge_id"]: row for row in supabase.table("badges").select("badge_id, name, description").execute().data}),
            lambda: supabase.table("user_streaks").select("streak_type, current_streak, longest_streak, last_completed_date")
                    .eq("user_id", uid).execute().data,
            lambda: checkin_days(supabase, uid, today),
        )
        owned = {row["avatar_id"] for row in owned_rows}
        if "starter" not in owned:   # the free starter avatar, given once
            supabase.table("user_avatars").upsert({"user_id": uid, "avatar_id": "starter"}, on_conflict="user_id,avatar_id").execute()
            owned.add("starter")
        badges = [
            {**badge_catalog[row["badge_id"]], "earned_at": row["earned_at"]}
            for row in earned if row["badge_id"] in badge_catalog
        ]
        for streak in streaks:
            last_day = streak.get("last_completed_date")
            if streak["streak_type"] == "workout" and last_day and date.fromisoformat(str(last_day)[:10]) < today - timedelta(days=1):
                streak["current_streak"] = 0
        # the daily check-in streak (any log) is still alive until a whole day passes with nothing
        days = streak_ending(checkins, today) or streak_ending(checkins, today - timedelta(days=1))
        streaks = [{"streak_type": "checkin", "current_streak": days}, *streaks]
        return {
            "fitcoins": game.get("fitcoins") or 0,
            "equipped_avatar": game.get("equipped_avatar") or "starter",
            "avatars": [{**avatar, "owned": avatar["id"] in owned,
                         "equipped": avatar["id"] == (game.get("equipped_avatar") or "starter")}
                        for avatar in AVATARS],
            "badges": badges,
            "streaks": streaks,
        }
    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to load avatars: {e.message}")


@router.post("/{user_id}/avatars/{avatar_id}/purchase")
def purchase_avatar(user_id: UUID, avatar_id: str, supabase: Client = Depends(get_supabase)):
    avatar = next((item for item in AVATARS if item["id"] == avatar_id), None)
    if avatar is None:
        raise HTTPException(status_code=404, detail="Avatar not found")
    try:
        _ensure_game_row(supabase, str(user_id))
        result = supabase.rpc("purchase_avatar", {
            "p_user_id": str(user_id), "p_avatar_id": avatar_id, "p_cost": avatar["cost"],
        }).execute().data[0]
        owned = {row["avatar_id"] for row in supabase.table("user_avatars").select("avatar_id").eq("user_id", str(user_id)).execute().data}
        unlocked = achievement_service.evaluate(supabase, str(user_id), "shop", extra={
            "purchased": result["purchased"], "owns_every_avatar": all(a["id"] in owned for a in AVATARS)})
        return {"purchased": result["purchased"], "fitcoins": result["fitcoins_balance"], "avatar_id": avatar_id,
                "achievements": unlocked}
    except APIError as e:
        if e.code == "P0001":
            raise HTTPException(status_code=402, detail="Not enough FitCoins")
        if e.code == FK_VIOLATION:
            raise HTTPException(status_code=404, detail="Profile not found")
        raise HTTPException(status_code=502, detail=f"Failed to purchase avatar: {e.message}")


@router.put("/{user_id}/avatars/{avatar_id}/equip")
def equip_avatar(user_id: UUID, avatar_id: str, supabase: Client = Depends(get_supabase)):
    if not any(item["id"] == avatar_id for item in AVATARS):
        raise HTTPException(status_code=404, detail="Avatar not found")
    uid = str(user_id)
    try:
        game = _ensure_game_row(supabase, uid)
        owned = supabase.table("user_avatars").select("avatar_id").eq(
            "user_id", uid
        ).eq("avatar_id", avatar_id).limit(1).execute().data
        if not owned:
            raise HTTPException(status_code=403, detail="Purchase this avatar before equipping it")
        changed = (game.get("equipped_avatar") or "starter") != avatar_id
        supabase.table("user_gamification").update({"equipped_avatar": avatar_id}).eq("user_id", uid).execute()
        unlocked = _avatar_changed(supabase, uid) if changed else []
        return {"equipped_avatar": avatar_id, "achievements": unlocked}
    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to equip avatar: {e.message}")


def _avatar_changed(supabase: Client, uid: str) -> list[dict]:
    """Count an avatar change toward Identity Crisis (three in a day)."""
    today = datetime.now(timezone.utc).date()
    changes = achievement_service.count_avatar_change(supabase, uid, today)
    return achievement_service.evaluate(supabase, uid, "avatar", today, {"changes_today": changes})


class AvatarBodyIn(BaseModel):
    body: Literal["male", "female"]


@router.put("/{user_id}/avatar-body")
def set_avatar_body(user_id: UUID, payload: AvatarBodyIn, supabase: Client = Depends(get_supabase)):
    """Which body the pixel avatar uses (male / female). Needs backend/sql/010_avatar_body.sql."""
    uid = str(user_id)
    try:
        game = _ensure_game_row(supabase, uid)
        changed = (game.get("avatar_body") or "male") != payload.body
        supabase.table("user_gamification").update({"avatar_body": payload.body}).eq("user_id", uid).execute()
        unlocked = _avatar_changed(supabase, uid) if changed else []
        return {"avatar_body": payload.body, "achievements": unlocked}
    except HTTPException:
        raise
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to save avatar body (has backend/sql/010_avatar_body.sql been run?): {e.message}")


@router.get("/{user_id}/achievements")
def get_achievements(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """Every achievement: earned ones with the System's commentary, the rest as goals or "???" with a hint.
    (The list is under "items", so the frontend doesn't announce them again.)"""
    try:
        exists, catalog = parallel(lambda: _profile_exists(supabase, user_id),
                                   lambda: achievement_service.catalog(supabase, str(user_id)))
        if not exists:
            raise HTTPException(status_code=404, detail="Profile not found")
        return catalog
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Failed to load achievements (has backend/sql/011_achievements.sql been run?): {e.message}")


DEMO_ACHIEVEMENT = "identity_crisis"


@router.post("/{user_id}/achievements/demo")
def demo_achievement(user_id: UUID, supabase: Client = Depends(get_supabase)):
    """For demos: earn Identity Crisis as if the avatar had changed three times today. Every press is
    announced as a first time, with its usual reward line; the reward itself is only paid once (paid: false
    after that), so the button can't be used to farm coins."""
    uid = str(user_id)
    if not _profile_exists(supabase, user_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    unlocked = achievement_service.evaluate(supabase, uid, "avatar", extra={"changes_today": 3}, only={DEMO_ACHIEVEMENT})
    if unlocked:
        return {"achievements": [{**unlocked[0], "paid": True}]}
    a = BY_CODE[DEMO_ACHIEVEMENT]
    xp, coins = a.reward
    return {"achievements": [{**achievement_service.announcement(a, uid, {"count": 3}, {"xp": xp, "fitcoins": coins}),
                              "paid": False}]}


@router.post("/{user_id}/points", response_model=AwardPointsOut)
def award_points(user_id: UUID, body: AwardPointsIn, supabase: Client = Depends(get_supabase)):
    """Add points to a user for completing an action."""
    try:
        result = award_action(supabase, str(user_id), body.action, body.source_id)
    except APIError as e:
        if e.code == FK_VIOLATION:
            raise HTTPException(status_code=404, detail="Profile not found")
        raise HTTPException(status_code=502, detail=f"Failed to award points: {e.message}")
    status = _status(user_id, result["total_points"], result["fitcoins_balance"])
    return {
        **status,
        "action": body.action,
        "points_awarded": result["points_awarded"],
        "awarded": result["awarded"],
        "previous_level": result["previous_level"],
        "leveled_up": result["level"] > result["previous_level"],
        "fitcoins_awarded": result["fitcoins_awarded"],
        "badges_earned": result["badges_earned"],
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
