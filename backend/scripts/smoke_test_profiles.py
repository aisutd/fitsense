"""Live smoke test for the profile endpoints against a running backend + real Supabase.

Usage:
    docker compose up -d --build
    python backend/scripts/smoke_test_profiles.py            # defaults to http://localhost:8000
    BASE_URL=http://host:port python backend/scripts/smoke_test_profiles.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

SAMPLE = {
    "age": 21,
    "height_cm": 175.3,
    "weight_kg": 70.2,
    "fitness_goal": "build_muscle",
    "fitness_level": "beginner",
    "workout_frequency": 4,
    "workout_location": "gym",
    "workout_preferences": ["strength", "cardio"],
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


def main():
    user_id = str(uuid.uuid4())
    print(f"Testing {BASE_URL} with user_id={user_id}\n")

    status, body = request("GET", "/health")
    check("health check", status == 200, body)

    status, body = request("GET", f"/profiles/{user_id}")
    check("GET before save returns 404", status == 404, f"{status} {body}")

    status, saved = request("PUT", f"/profiles/{user_id}", SAMPLE)
    check("PUT saves profile", status == 200, f"{status} {saved}")
    for key, value in SAMPLE.items():
        check(f"  saved {key} matches", saved[key] == value, f"expected {value!r}, got {saved[key]!r}")

    status, fetched = request("GET", f"/profiles/{user_id}")
    check("GET returns stored profile", status == 200 and fetched == saved, f"{status} {fetched}")

    status, updated = request("PUT", f"/profiles/{user_id}", {**SAMPLE, "weight_kg": 68.5})
    check("PUT overwrites existing profile", status == 200 and updated["weight_kg"] == 68.5, f"{status} {updated}")
    check("  created_at preserved", updated["created_at"] == saved["created_at"], updated)
    check("  updated_at advanced", updated["updated_at"] > saved["updated_at"], updated)

    status, body = request("PUT", f"/profiles/{uuid.uuid4()}", {**SAMPLE, "age": 5})
    check("invalid data rejected with 422", status == 422, f"{status} {body}")

    print(f"\nAll checks passed. Row is visible in Supabase > Table Editor > profiles (user_id={user_id}).")


if __name__ == "__main__":
    main()
