"""Give a player the achievements their history has already earned, without announcing them.

Achievements are normally checked as things happen. This replays every day the player logged something,
oldest first, through the same checks (app/achievements.py), then the league and shop ones once with
how things stand now. Each achievement is awarded on the first day it was earned, with its usual
reward, and dated to that day so the League tab lists them in order. Already-earned ones are skipped,
so it's safe to re-run.

The logs are loaded once and the checks run in memory (one player's years of logs would otherwise be
thousands of queries). Run inside the backend container, where the app and the Supabase keys are:
    docker compose cp backend/scripts/backfill_achievements.py backend:/tmp/
    docker compose exec backend python /tmp/backfill_achievements.py --username Prat [--dry-run]
"""

import argparse
import bisect
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from functools import cached_property

sys.path.insert(0, "/app")
from app import achievement_service as svc  # noqa: E402
from app import healthscore_repo as repo  # noqa: E402
from app.achievements import ACHIEVEMENTS, LOG_TRIGGERS  # noqa: E402
from app.database import get_supabase  # noqa: E402
from app.gamification import AVATARS, LEAGUES  # noqa: E402
from app.gamification_service import CHECKIN_DATES  # noqa: E402

COLUMNS = {
    "workout_logs": ("workout_date", "workout_date, completion_status, duration_minutes, plan_id"),
    "sleep_logs": ("sleep_date", "sleep_date, hours_slept, sleep_quality"),
    "activity_logs": ("log_date", "log_date, steps, active_minutes"),
    "meal_entries": ("log_date", "log_date, meal_type, display_name, protein_g, calories"),
}


def all_rows(db, table, columns, uid, **filters):
    def query():
        q = db.table(table).select(columns).eq("user_id", uid)
        for key, value in filters.items():
            q = q.eq(key, value)
        return q.order(COLUMNS.get(table, ("user_id",))[0])
    return repo.all_rows(query)


class History:
    """Everything one player has logged, loaded once."""

    def __init__(self, db, uid):
        self.uid = uid
        self.rows = {t: all_rows(db, t, cols, uid, **({"status": "confirmed"} if t == "meal_entries" else {}))
                     for t, (_, cols) in COLUMNS.items()}
        self.by_day = {t: defaultdict(list) for t in COLUMNS}
        for t, (col, _) in COLUMNS.items():
            for r in self.rows[t]:
                self.by_day[t][svc._day(r[col])].append(r)
        profile = repo.get_profile(db, uid)
        self.goals = repo.current_goals(db, uid, profile)
        self.plans = {svc._day(r["week_start"]): int(r["days_per_week"])
                      for r in all_rows(db, "workout_plans", "week_start, days_per_week", uid)}
        # check-in days: anything logged; last night's sleep counts for the day you woke up
        shift = {t: s for t, _, s in CHECKIN_DATES}
        self.checkins = sorted({d + timedelta(days=shift[t]) for t in COLUMNS for d in self.by_day[t]})
        self.checkin_set = set(self.checkins)
        # for the HealthScore checks, scored the same way as the app (healthscore_repo.score)
        self.user_ctx = repo.load_contexts(db, uid)[uid]
        self.weights, _ = repo.active_weights(db)
        first, last = (self.checkins[0], self.checkins[-1]) if self.checkins else (date.today(), date.today())
        self.score_logs = repo.load_logs(db, first - timedelta(days=7), last, uid)[uid]

    def streak(self, day):
        n = 0
        while day - timedelta(days=n) in self.checkin_set:
            n += 1
        return n


class MemoryContext(svc.Context):
    """svc.Context, answered from History instead of the database."""

    def __init__(self, history: History, trigger, day, extra=None):
        super().__init__(None, history.uid, trigger, day, extra)
        self.h = history

    def _window(self, table):
        start = self.day - timedelta(days=svc.HISTORY_DAYS)
        return [r for d in sorted(self.h.by_day[table]) if start <= d <= self.day for r in self.h.by_day[table][d]]

    @cached_property
    def workouts(self):
        return self._window("workout_logs")

    @cached_property
    def _sleep(self):
        return {svc._day(r["sleep_date"]): r for r in self._window("sleep_logs")}

    @cached_property
    def _activity(self):
        return {svc._day(r["log_date"]): r for r in self._window("activity_logs")}

    @cached_property
    def _meals(self):
        out = {}
        for r in self._window("meal_entries"):
            out.setdefault(svc._day(r["log_date"]), []).append(r)
        return out

    @cached_property
    def goals(self):
        return self.h.goals

    def plan_days(self):
        return self.h.plans.get(self.day - timedelta(days=self.day.weekday()))

    def day_score(self):
        if self._score is None:
            self._score = repo.score(self.h.user_ctx, self.h.score_logs, self.h.weights, self.log_day, self.log_day, day=True)
        return self._score

    def last_log_before(self, day):
        i = bisect.bisect_left(self.h.checkins, day)
        return self.h.checkins[i - 1] if i else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = get_supabase()
    account = db.table("accounts").select("user_id").eq("username", args.username.lower()).limit(1).execute().data
    if not account:
        sys.exit(f"No account called {args.username}")
    uid = account[0]["user_id"]
    svc.sync_catalog(db)
    earned = set(svc._earned(db, uid))
    print(f"{args.username}: {len(earned)} achievements earned so far; loading history ...")
    h = History(db, uid)
    print(f"  {len(h.checkins)} days with logs, {h.checkins[0] if h.checkins else '-'} to {h.checkins[-1] if h.checkins else '-'}")

    found = []   # (day, achievement, facts)
    log_days = sorted({d for t in COLUMNS for d in h.by_day[t]})
    trigger_of = {"workout_logs": "workout", "sleep_logs": "sleep", "activity_logs": "activity", "meal_entries": "meal"}
    for day in log_days:
        for table, trigger in trigger_of.items():
            if not h.by_day[table].get(day):
                continue
            ctx = MemoryContext(h, trigger, day)
            ctx.extra["checkin_streak"] = h.streak(ctx.log_day)
            for a in ACHIEVEMENTS:
                if a.code in earned or trigger not in a.triggers:
                    continue
                facts = a.check(ctx)
                if facts is not None:
                    found.append((ctx.log_day, a, facts))
                    earned.add(a.code)

    # league and shop: as things stand now
    game = db.table("user_gamification").select("league_tier").eq("user_id", uid).limit(1).execute().data
    tier = int((game[0].get("league_tier") if game else 0) or 0)
    owned = {r["avatar_id"] for r in db.table("user_avatars").select("avatar_id").eq("user_id", uid).execute().data}
    now = {"tier": tier, "league": LEAGUES[tier], "previous_tier": None,
           "purchased": bool(owned - {"starter"}), "owns_every_avatar": all(a["id"] in owned for a in AVATARS)}
    today = datetime.now(timezone.utc).date()
    for a in ACHIEVEMENTS:
        if a.code not in earned and a.triggers & {"league", "shop"} and not a.triggers & LOG_TRIGGERS:
            facts = a.check(MemoryContext(h, next(iter(a.triggers)), today, now))
            if facts is not None:
                found.append((today, a, facts))
                earned.add(a.code)

    print(f"  {len(found)} to award:")
    for day, a, facts in found:
        print(f"    {day}  {a.rarity:9} {a.name}  {svc._fill(a.description, facts)}")
    if args.dry_run or not found:
        return
    for day, a, facts in found:
        if svc.award(db, uid, a, facts):
            stamp = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).isoformat()
            db.table("user_achievements").update({"completed_at": stamp, "last_progress_at": stamp}).eq(
                "user_id", uid).eq("achievement_id", svc.achievement_id(a.code)).execute()
    print(f"  awarded {len(found)} (no announcements); now {len(svc._earned(db, uid))} earned")


if __name__ == "__main__":
    main()
