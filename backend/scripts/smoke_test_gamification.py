"""Live smoke test for the gamification endpoints against a running backend + real Supabase.

Requires backend/sql/002_data_model.sql and 003_gamification_points.sql to be applied.

Usage:
    docker compose up -d --build
    python backend/scripts/smoke_test_gamification.py        # defaults to http://localhost:8000
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

PROFILE = {
    "name": "Smoke Test",
    "age": 21,
    "height_cm": 175.0,
    "weight_kg": 70.0,
    "fitness_goal": "build_muscle",
    "fitness_level": "beginner",
    "workout_frequency": 4,
    "workout_location": "gym",
    "workout_preferences": ["strength"],
}


def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        print(f"       {detail}")
        sys.exit(1)


def award(user_id, action, source_id=None):
    body = {"action": action} if source_id is None else {"action": action, "source_id": source_id}
    return request("POST", f"/gamification/{user_id}/points", body)


def main():
    user_id = str(uuid.uuid4())
    print(f"Testing {BASE_URL} with user_id={user_id}\n")

    status, body = request("PUT", f"/profiles/{user_id}", PROFILE)
    check("profile created (with name, synced to user_preferences)", status == 200 and body["name"] == "Smoke Test", f"{status} {body}")

    status, body = request("GET", f"/gamification/{user_id}")
    check("new user starts at 0 points, level 1", status == 200 and body["total_points"] == 0 and body["level"] == 1, f"{status} {body}")

    status, body = award(user_id, "onboarding_completed")
    check("onboarding +100", status == 200 and body["total_points"] == 100, f"{status} {body}")
    award(user_id, "workout_completed", "smoke-w1")
    status, body = award(user_id, "workout_completed", "smoke-w2")
    check("two workouts -> 200 points, level 2, leveled up", body["total_points"] == 200 and body["level"] == 2 and body["leveled_up"], body)

    status, body = award(user_id, "workout_completed", "smoke-w3")
    check("task example: workout +50 -> 250 points, level 2",
          status == 200 and body["points_awarded"] == 50 and body["total_points"] == 250 and body["level"] == 2, f"{status} {body}")

    status, body = award(user_id, "workout_completed", "smoke-w3")
    check("same workout again is not rewarded twice", body["awarded"] is False and body["total_points"] == 250, body)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: award(user_id, "meal_logged"), range(10)))
    check("10 concurrent +10 awards all succeed", all(s == 200 for s, _ in results), results)

    status, body = request("GET", f"/gamification/{user_id}")
    check("stored total is exact after concurrent awards (350)", status == 200 and body["total_points"] == 350, f"{status} {body}")
    check("  level 2, 150 points to level 3", body["level"] == 2 and body["points_to_next_level"] == 150, body)

    status, events = request("GET", f"/gamification/{user_id}/history?limit=100")
    check("history has every award (14 events, 350 points)",
          status == 200 and len(events) == 14 and sum(e["points"] for e in events) == 350, f"{status} {len(events) if isinstance(events, list) else events}")

    status, body = award(str(uuid.uuid4()), "workout_completed")
    check("unknown user -> 404", status == 404, f"{status} {body}")

    status, body = request("POST", f"/gamification/{user_id}/points", {"action": "workout_completed", "points": 99999})
    check("custom point amounts rejected (422)", status == 422, f"{status} {body}")

    print(f"\nAll checks passed. See Supabase > Table Editor > user_gamification / xp_events (user_id={user_id}).")


if __name__ == "__main__":
    main()
