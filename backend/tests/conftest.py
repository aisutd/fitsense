import json
import re
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.database import get_supabase
from app.main import app

# Upsert conflict keys and generated primary keys, mirroring the SQL schema.
UPSERT_KEYS = {
    "profiles": ("user_id",),
    "user_preferences": ("user_id",),
    "user_gamification": ("user_id",),
    "sleep_logs": ("user_id", "sleep_date"),
    "activity_logs": ("user_id", "log_date"),
    "fdc_foods": ("fdc_id",),
    "fdc_search_cache": ("query",),
}
GENERATED_IDS = {
    "workout_logs": "workout_log_id",
    "workout_plans": "plan_id",
    "meal_entries": "meal_id",
    "nutrition_goals": "nutrition_goal_id",
    "sleep_goals": "sleep_goal_id",
    "progress_goals": "progress_goal_id",
    "health_scores": "score_id",
    "health_score_config": "config_id",
    "xp_events": "event_id",
    "accounts": "user_id",
    "meal_items": "meal_item_id",
    "fdc_food_portions": "portion_id",
}
UNIQUE_COLUMNS = {"accounts": "username"}
TIMESTAMP_COLUMNS = {"health_scores": "calculated_at"}

_clock = count()
_epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _now() -> str:
    """Strictly increasing timestamps so 'newest row' ordering is deterministic."""
    return (_epoch + timedelta(milliseconds=next(_clock))).isoformat()


class FakeQuery:
    """Mimics the subset of the supabase-py query builder used by the routers."""

    def __init__(self, db: "FakeSupabase", name: str):
        self.db = db
        self.name = name
        self.rows = db.tables.setdefault(name, {})
        self.op = None
        self.payload = None
        self.on_conflict = None
        self.filters = []
        self.order_by = None
        self.max_rows = None

    # writes
    def upsert(self, row, on_conflict=None):
        self.op, self.payload = "upsert", row
        self.on_conflict = tuple(on_conflict.split(",")) if on_conflict else UPSERT_KEYS[self.name]
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    # reads
    def select(self, *_):
        self.op = "select"
        return self

    def eq(self, column, value):
        self.filters.append((column, lambda a, b: a == b, value))
        return self

    def gte(self, column, value):
        self.filters.append((column, lambda a, b: a >= b, value))
        return self

    def lte(self, column, value):
        self.filters.append((column, lambda a, b: a <= b, value))
        return self

    def in_(self, column, values):
        self.filters.append((column, lambda a, b: a in b, [str(v) for v in values]))
        return self

    def order(self, column, desc=False):
        self.order_by = (column, desc)
        return self

    def limit(self, n):
        self.max_rows = n
        return self

    def _check_fk(self, row):
        if self.name != "profiles" and "user_id" in row and row["user_id"] not in self.db.tables.get("profiles", {}):
            raise APIError({"code": "23503", "message": "violates foreign key constraint"})

    def execute(self):
        if self.op == "upsert" and isinstance(self.payload, list):
            rows = []
            for payload in self.payload:
                q = FakeQuery(self.db, self.name)
                q.op, q.payload, q.on_conflict = "upsert", payload, self.on_conflict
                rows += q.execute().data
            return SimpleNamespace(data=rows)
        if self.op == "upsert":
            self._check_fk(self.payload)
            key = tuple(self.payload[c] for c in self.on_conflict)
            key = key[0] if len(key) == 1 else key
            existing = self.rows.get(key, {})
            stamps = {}
            if self.name == "profiles":
                now = _now()
                stamps = {"created_at": existing.get("created_at", now), "updated_at": now}
            self.rows[key] = {**existing, **self.payload, **stamps}
            return SimpleNamespace(data=[self.rows[key]])
        if self.op == "insert":
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for payload in payloads:
                self._check_fk(payload)
                unique = UNIQUE_COLUMNS.get(self.name)
                if unique and any(r[unique] == payload[unique] for r in self.rows.values()):
                    raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
                id_col = GENERATED_IDS[self.name]
                row = {id_col: str(uuid4()), TIMESTAMP_COLUMNS.get(self.name, "created_at"): _now(), **payload}
                self.rows[row[id_col]] = row
                inserted.append(row)
            return SimpleNamespace(data=inserted)

        def matches(r):
            return all(c in r and r[c] is not None and op(str(r[c]), v if isinstance(v, list) else str(v))
                       for c, op, v in self.filters)

        result = [r for r in self.rows.values() if matches(r)]
        if self.op == "delete":
            for key in [k for k, r in self.rows.items() if matches(r)]:
                del self.rows[key]
            return SimpleNamespace(data=result)
        if self.op == "update":
            for r in result:
                r.update(self.payload)
            return SimpleNamespace(data=result)
        if self.order_by:
            column, desc = self.order_by
            result.sort(key=lambda r: r[column], reverse=desc)
        if self.max_rows is not None:
            result = result[: self.max_rows]
        return SimpleNamespace(data=result)


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


class FakeSearchRpc:
    """In-memory search_fdc_foods(): every word must start a word of the description (no typo matching)."""

    def __init__(self, db: "FakeSupabase", params: dict):
        self.db = db
        self.params = params

    def execute(self):
        words = [w.lower() for w in self.params["words"] if w]
        out = []
        for r in self.db.tables.get("fdc_foods", {}).values():
            desc_words = re.findall(r"[a-z0-9]+", r["description"].lower())
            if r.get("calories_per_100g") is not None and words and all(
                    any(d.startswith(w) for d in desc_words) for w in words):
                out.append({k: r.get(k) for k in ("fdc_id", "description", "data_type", "calories_per_100g")})
        out.sort(key=lambda r: len(r["description"]))
        return SimpleNamespace(data=out[: self.params.get("max_results", 150)])


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, dict] = {}

    def table(self, name):
        return FakeQuery(self, name)

    def rpc(self, name, params):
        if name == "search_fdc_foods":
            return FakeSearchRpc(self, params)
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


# --- FoodData Central fake (recorded responses in tests/fixtures/fdc) -------------------

FDC_FIXTURES = Path(__file__).parent / "fixtures" / "fdc"


class FakeFdc:
    """Serves recorded FDC responses; counts calls so tests can check caching."""

    def __init__(self):
        self.calls = []

    def food(self, fdc_id: int):
        from app.food.fdc import parse_food
        self.calls.append(("food", fdc_id))
        path = FDC_FIXTURES / f"food_{fdc_id}.json"
        if not path.exists():
            from app.food.fdc import FdcError
            raise FdcError("Food not found in FoodData Central")
        return parse_food(json.loads(path.read_text(encoding="utf-8")))

    def search_ranked(self, query: str):
        from app.food.fdc import SearchHit, rank_hits
        self.calls.append(("search", query))
        path = FDC_FIXTURES / f"search_{query.replace(' ', '_')}.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        hits = []
        for group in ("preferred", "fallback"):
            for f in data[group]["foods"]:
                kcal = next((n.get("value") for n in f["foodNutrients"] if n.get("nutrientNumber") == "208"), None)
                hits.append(SearchHit(f["fdcId"], f["description"], f["dataType"], kcal, float(f.get("score") or 0)))
        return rank_hits(query, hits)


@pytest.fixture
def fake_fdc():
    from app.routers.meals import get_fdc
    fdc = FakeFdc()
    app.dependency_overrides[get_fdc] = lambda: fdc
    yield fdc


@pytest.fixture
def usda_copy(fake_db):
    """The local USDA copy, imported (with the real importer) from the recorded FDC foods."""
    from app.food.fdc_import import import_foods
    raws = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FDC_FIXTURES.glob("food_*.json"))]
    import_foods(fake_db, raws, log=lambda *_: None)
    return fake_db
