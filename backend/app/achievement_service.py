"""Checks, awards and lists the System's achievements (app/achievements.py).

evaluate() runs after a log, a league view, a purchase or an avatar change: only the achievements that
kind of event can trigger and that the player hasn't earned yet. Data is loaded lazily, once per
evaluation. Each award goes through award_achievement() (backend/sql/011_achievements.sql), which
records it once and adds its XP and FitCoins in one step. Achievements never get in the way: if
anything fails here (say 011 hasn't been run yet), the log or page still works and nothing is announced.
"""

import logging
import random
from datetime import date, datetime, timedelta, timezone
from functools import cached_property
from uuid import NAMESPACE_URL, uuid5

from app import healthscore_repo as repo
from app.achievements import ACHIEVEMENTS, BY_CODE, RARITIES, Achievement
from app.gamification import LEVEL_THRESHOLDS

log = logging.getLogger(__name__)

HISTORY_DAYS = 42   # enough for the longest check (two weeks of meals) plus the week before
SYNCED_ATTR = "_fitsense_achievements_synced"


def achievement_id(code: str) -> str:
    """A fixed id per code, so the catalog can be upserted without looking ids up."""
    return str(uuid5(NAMESPACE_URL, f"fitsense:achievement:{code}"))


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


class Context:
    """What the checks can look at. `day` is the date the event is for (for sleep, the night it
    started); everything is loaded on first use."""

    def __init__(self, db, user_id: str, trigger: str, day: date, extra: dict | None = None):
        self.db, self.user_id, self.trigger, self.day = db, user_id, trigger, day
        self.extra = extra or {}
        # the day this counts as a check-in for: last night's sleep counts for the day you woke up
        self.log_day = day + timedelta(days=1) if trigger == "sleep" else day
        self._score = None

    date_of = staticmethod(_day)

    def _rows(self, table, column, columns, **filters):
        q = (self.db.table(table).select(columns).eq("user_id", self.user_id)
             .gte(column, (self.day - timedelta(days=HISTORY_DAYS)).isoformat()).lte(column, self.day.isoformat()))
        for key, value in filters.items():
            q = q.eq(key, value)
        return sorted(q.execute().data, key=lambda r: str(r[column]))

    @cached_property
    def workouts(self):
        return self._rows("workout_logs", "workout_date", "workout_date, completion_status, duration_minutes, plan_id")

    @cached_property
    def _sleep(self):
        return {_day(r["sleep_date"]): r for r in self._rows("sleep_logs", "sleep_date", "sleep_date, hours_slept, sleep_quality")}

    @cached_property
    def _activity(self):
        return {_day(r["log_date"]): r for r in self._rows("activity_logs", "log_date", "log_date, steps, active_minutes")}

    @cached_property
    def _meals(self):
        by_day = {}
        for r in self._rows("meal_entries", "log_date", "log_date, meal_type, display_name, protein_g, calories",
                            status="confirmed"):
            by_day.setdefault(_day(r["log_date"]), []).append(r)
        return by_day

    def sleep_on(self, night: date):
        return self._sleep.get(night)

    def steps_on(self, day: date):
        row = self._activity.get(day)
        return int(row["steps"]) if row and row.get("steps") is not None else None

    def meals_on(self, day: date):
        return self._meals.get(day, [])

    @cached_property
    def goals(self):
        return repo.current_goals(self.db, self.user_id, repo.get_profile(self.db, self.user_id))

    def plan_days(self) -> int | None:
        """How many workouts this week's plan has (None without a plan)."""
        monday = self.day - timedelta(days=self.day.weekday())
        rows = (self.db.table("workout_plans").select("days_per_week").eq("user_id", self.user_id)
                .eq("week_start", monday.isoformat()).limit(1).execute().data)
        return int(rows[0]["days_per_week"]) if rows else None

    def day_score(self):
        """The HealthScore of the check-in day."""
        if self._score is None:
            self._score = repo.calculate(self.db, self.user_id, "day", self.log_day)[0]
        return self._score

    def last_log_before(self, day: date) -> date | None:
        """The latest check-in day before `day` with anything logged."""
        latest = None
        for table, column, shift in (("workout_logs", "workout_date", 0), ("activity_logs", "log_date", 0),
                                     ("meal_entries", "log_date", 0), ("sleep_logs", "sleep_date", 1)):
            q = (self.db.table(table).select(column).eq("user_id", self.user_id)
                 .lte(column, (day - timedelta(days=1 + shift)).isoformat()))
            if table == "meal_entries":
                q = q.eq("status", "confirmed")
            rows = q.order(column, desc=True).limit(1).execute().data
            if rows:
                found = _day(rows[0][column]) + timedelta(days=shift)
                latest = found if latest is None or found > latest else latest
        return latest


# --- the catalog and awards ----------------------------------------------------------------------

def sync_catalog(db) -> None:
    """Upsert the achievements into the achievements table (once per database client)."""
    if getattr(db, SYNCED_ATTR, False):
        return
    rows = [{"achievement_id": achievement_id(a.code), "code": a.code, "name": a.name, "description": a.plain,
             "kind": "one_time", "category": a.category, "is_hidden": a.hidden, "rarity": a.rarity}
            for a in ACHIEVEMENTS]
    db.table("achievements").upsert(rows, on_conflict="code").execute()
    setattr(db, SYNCED_ATTR, True)


def _earned(db, user_id: str) -> dict[str, dict]:
    """{code: user_achievements row} for what the player has earned."""
    codes = {achievement_id(a.code): a.code for a in ACHIEVEMENTS}
    rows = (db.table("user_achievements").select("achievement_id, completed_at, current_value, facts")
            .eq("user_id", user_id).execute().data)
    return {codes[r["achievement_id"]]: r for r in rows if r["achievement_id"] in codes and r.get("completed_at")}


def _commentary(a: Achievement, user_id: str) -> str:
    """The System's line for this player (the same one every time they look)."""
    return random.Random(f"{user_id}:{a.code}").choice(a.lines)


def _fill(text: str, facts: dict) -> str:
    try:
        return text.format(**facts)
    except (KeyError, IndexError, ValueError):
        return text


def announcement(a: Achievement, user_id: str, facts: dict | None = None, reward: dict | None = None) -> dict:
    facts = facts or {}
    return {
        "code": a.code, "name": a.name, "rarity": a.rarity, "category": a.category,
        "description": _fill(a.description, facts), "plain": a.plain,
        "commentary": _fill(_commentary(a, user_id), facts),
        "rewarded": a.rewarded, "reward": reward,
    }


def award(db, user_id: str, a: Achievement, facts: dict) -> dict | None:
    """Record the achievement and pay its reward. None if it was already earned."""
    xp, coins = a.reward
    facts = {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in facts.items()}
    result = db.rpc("award_achievement", {
        "p_user_id": user_id, "p_achievement_id": achievement_id(a.code), "p_xp": xp, "p_fitcoins": coins,
        "p_level_thresholds": LEVEL_THRESHOLDS, "p_facts": facts,
    }).execute().data[0]
    if not result["awarded"]:
        return None
    reward = {"xp": xp, "fitcoins": coins, "fitcoins_balance": result["fitcoins_balance"],
              "level": result["new_level"], "previous_level": result["previous_level"]} if a.rewarded else None
    return announcement(a, user_id, facts, reward)


def evaluate(db, user_id: str, trigger: str, day: date | None = None, extra: dict | None = None,
             only: set[str] | None = None) -> list[dict]:
    """Award every not-yet-earned achievement this event triggers. Returns their announcements,
    rarest first. Never raises."""
    try:
        sync_catalog(db)
        earned = _earned(db, user_id)
        candidates = [a for a in ACHIEVEMENTS if trigger in a.triggers and a.code not in earned
                      and (only is None or a.code in only)]
        if not candidates:
            return []
        ctx = Context(db, user_id, trigger, day or datetime.now(timezone.utc).date(), extra)
        unlocked = []
        for a in candidates:
            try:
                facts = a.check(ctx)
            except Exception:   # one broken check shouldn't stop the others
                log.exception("achievement check %s failed", a.code)
                continue
            if facts is not None:
                done = award(db, user_id, a, facts)
                if done:
                    unlocked.append(done)
        return sorted(unlocked, key=lambda x: -RARITIES.index(x["rarity"]))
    except Exception:
        log.exception("achievements for %s (%s) failed", user_id, trigger)
        return []


def count_avatar_change(db, user_id: str, today: date) -> int:
    """Count an avatar change (equip or body) toward today's Identity Crisis; returns today's count."""
    aid = achievement_id("identity_crisis")
    try:
        sync_catalog(db)
        rows = (db.table("user_achievements").select("current_value, last_progress_at, completed_at")
                .eq("user_id", user_id).eq("achievement_id", aid).limit(1).execute().data)
        row = rows[0] if rows else {}
        same_day = row.get("last_progress_at") and _day(row["last_progress_at"]) == today
        count = int(row.get("current_value") or 0) + 1 if same_day else 1
        db.table("user_achievements").upsert({
            "user_id": user_id, "achievement_id": aid, "current_value": count,
            "last_progress_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,achievement_id").execute()
        return count
    except Exception:
        log.exception("counting avatar changes for %s failed", user_id)
        return 0


def catalog(db, user_id: str) -> dict:
    """Every achievement for the League tab: earned ones in full, the rest as goals or "???"."""
    sync_catalog(db)
    earned = _earned(db, user_id)
    got, goals, secrets = [], [], []
    for a in ACHIEVEMENTS:
        row = earned.get(a.code)
        if row:
            xp, coins = a.reward
            got.append({**announcement(a, user_id, row.get("facts") or {}), "earned": True, "earned_at": row["completed_at"],
                        "reward": {"xp": xp, "fitcoins": coins} if a.rewarded else None})
        elif a.hidden:
            secrets.append({"code": a.code, "name": "???", "rarity": a.rarity, "category": a.category,
                            "hint": a.hint, "earned": False, "hidden": True})
        else:
            goals.append({"code": a.code, "name": a.name, "rarity": a.rarity, "category": a.category,
                          "plain": a.plain, "earned": False, "hidden": False})
    got.sort(key=lambda i: str(i["earned_at"]), reverse=True)   # newest first
    by_rarity = lambda i: RARITIES.index(i["rarity"])            # noqa: E731
    items = got + sorted(goals, key=by_rarity) + sorted(secrets, key=by_rarity)
    counts = {r: {"earned": sum(1 for i in items if i["rarity"] == r and i["earned"]),
                  "total": sum(1 for i in items if i["rarity"] == r)} for r in RARITIES}
    return {"items": items, "earned": len(earned), "total": len(ACHIEVEMENTS), "by_rarity": counts}
