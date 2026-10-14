from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.database import get_supabase
from app.main import app

PRIMARY_KEYS = {"profiles": "user_id", "user_preferences": "user_id", "user_gamification": "user_id"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeQuery:
    """Mimics the subset of the supabase-py query builder used by the routers."""

    def __init__(self, name: str, rows: dict):
        self.name = name
        self.rows = rows
        self.op = None
        self.payload = None
        self.filters = {}
        self.order_by = None
        self.max_rows = None

    def upsert(self, row, on_conflict=None):
        self.op, self.payload = "upsert", row
        return self

    def select(self, *_):
        self.op = "select"
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def order(self, column, desc=False):
        self.order_by = (column, desc)
        return self

    def limit(self, n):
        self.max_rows = n
        return self

    def execute(self):
        if self.op == "upsert":
            key = self.payload[PRIMARY_KEYS[self.name]]
            existing = self.rows.get(key, {})
            now = _now()
            stamps = {"created_at": existing.get("created_at", now), "updated_at": now} if self.name == "profiles" else {}
            self.rows[key] = {**existing, **self.payload, **stamps}
            return SimpleNamespace(data=[self.rows[key]])
        matches = [r for r in self.rows.values() if all(str(r[k]) == str(v) for k, v in self.filters.items())]
        if self.order_by:
            column, desc = self.order_by
            matches.sort(key=lambda r: r[column], reverse=desc)
        if self.max_rows is not None:
            matches = matches[: self.max_rows]
        return SimpleNamespace(data=matches)


class FakeRpc:
    """In-memory version of the award_points() SQL function."""

    def __init__(self, db: "FakeSupabase", params: dict):
        self.db = db
        self.params = params

    def execute(self):
        p = self.params
        user_id = p["p_user_id"]
        if user_id not in self.db.tables.setdefault("profiles", {}):
            raise APIError({"code": "23503", "message": "violates foreign key constraint"})
        events = self.db.tables.setdefault("xp_events", {})
        duplicate = p["p_source_id"] is not None and any(
            e["user_id"] == user_id and e["action"] == p["p_action"] and e["source_id"] == p["p_source_id"]
            for e in events.values()
        )
        game = self.db.tables.setdefault("user_gamification", {})
        row = game.setdefault(user_id, {"user_id": user_id, "total_xp": 0, "level": 1})
        previous = row["level"]
        if not duplicate:
            event_id = str(uuid4())
            events[event_id] = {
                "event_id": event_id, "user_id": user_id, "action": p["p_action"],
                "points": p["p_points"], "source_id": p["p_source_id"], "created_at": _now(),
            }
            row["total_xp"] += p["p_points"]
            row["level"] = max(1, sum(1 for t in p["p_level_thresholds"] if t <= row["total_xp"]))
        return SimpleNamespace(data=[{
            "new_total_xp": row["total_xp"], "new_level": row["level"],
            "previous_level": previous, "awarded": not duplicate,
        }])


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, dict] = {}

    def table(self, name):
        return FakeQuery(name, self.tables.setdefault(name, {}))

    def rpc(self, name, params):
        assert name == "award_points"
        return FakeRpc(self, params)


@pytest.fixture
def fake_db():
    db = FakeSupabase()
    app.dependency_overrides[get_supabase] = lambda: db
    yield db
    app.dependency_overrides.clear()


@pytest.fixture
def client(fake_db):
    return TestClient(app)
