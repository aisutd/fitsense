"""Create sample players (with logins) and realistic logs, then check their HealthScores.

Runs against a live backend + Supabase (needs backend/sql/001-005 applied).

Usage:
    docker compose up -d --build
    python backend/scripts/seed_sample_users.py          # BASE_URL defaults to http://localhost:8000
    # then log in at http://localhost:5173 as ava, ben, cara or dev with SAMPLE_PASSWORD

Re-running reuses accounts that already exist and leaves their data alone.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
TODAY = date.today()

# Test-only password shared by the sample players. Never use a real password here.
SAMPLE_PASSWORD = "fitsense-sample"

BASE_PROFILE = {
    "age": 24,
    "height_cm": 175.0,
    "weight_kg": 72.0,
    "fitness_goal": "general_fitness",
    "fitness_level": "intermediate",
    "workout_frequency": 4,
    "workout_location": "gym",
    "workout_preferences": ["strength", "cardio"],
}
GOALS = {
    "nutrition": {"daily_calorie_target": 2000, "protein_target_g": 150, "carbs_target_g": 250, "fat_target_g": 67},
    "sleep_target_hours": 8,
    "daily_steps": 8000,
}


def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def ok(method, path, body=None):
    status, data = request(method, path, body)
    if status not in (200, 201):
        sys.exit(f"[FAIL] {method} {path} -> {status} {data}")
    return data


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def create_user(name, **profile):
    """Sign up as name.lower() and complete onboarding. Returns None if the account already exists."""
    username = name.lower()
    status, account = request("POST", "/auth/signup", {"username": username, "password": SAMPLE_PASSWORD})
    if status == 409:
        print(f"{name} - account already exists, skipping (log in as '{username}')")
        return None
    if status != 201:
        sys.exit(f"[FAIL] signup {name} -> {status} {account}")
    uid = account["user_id"]
    ok("PUT", f"/profiles/{uid}", {**BASE_PROFILE, "name": name, **profile})
    login = ok("POST", "/auth/login", {"username": username, "password": SAMPLE_PASSWORD})
    if login["user_id"] != uid or not login["has_profile"]:
        sys.exit(f"[FAIL] login {name} -> {login}")
    return uid


def log_days(uid, days, *, workouts=(), sleep=None, steps=None, meal=None, goals=True):
    if goals:
        ok("PUT", f"/goals/{uid}", GOALS)
    for n in workouts:
        ok("POST", f"/logs/{uid}/workouts", {"workout_date": day(n), "completion_status": "completed", "duration_minutes": 45})
    for n in days:
        if sleep is not None:
            ok("PUT", f"/logs/{uid}/sleep/{day(n)}", {"hours_slept": sleep, "sleep_quality": 4})
        if steps is not None:
            ok("PUT", f"/logs/{uid}/activity/{day(n)}", {"steps": steps})
        if meal is not None:
            ok("POST", f"/logs/{uid}/meals", {"log_date": day(n), "meal_type": "lunch", "display_name": "Daily meals", **meal})


def check(label, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        print(f"         {detail}")
        sys.exit(1)


def week(uid, range_="week"):
    return ok("GET", f"/healthscore/{uid}?range={range_}&end_date={TODAY}")


def main():
    print(f"Seeding sample players on {BASE_URL} (today = {TODAY})\n")
    users = []

    # 1. On track: every planned workout, 8 h sleep, 9,000 steps, meals on target.
    ava = create_user("Ava")
    if ava:
        log_days(ava, range(7), workouts=(0, 2, 4, 6), sleep=8, steps=9000,
                 meal={"calories": 2000, "protein_g": 150, "carbs_g": 250, "fat_g": 67})
        s = week(ava)
        print("Ava - on track")
        check("all four categories, score 100", s["overall_score"] == 100 and not s["provisional"], s)
        users.append(("ava", "on track", s))

        # Last week was rougher, so the range selector shows a difference.
        log_days(ava, range(7, 14), workouts=(8, 11), sleep=6.5, steps=5000,
                 meal={"calories": 2600, "protein_g": 90, "carbs_g": 330, "fat_g": 95}, goals=False)
        check("previous 7 days score lower than this week", week(ava, "last-week")["overall_score"] < 100)
        snap = ok("POST", f"/healthscore/{ava}/snapshots?range=week&end_date={TODAY}")
        history = ok("GET", f"/healthscore/{ava}/history")
        check("snapshot saved to health_scores", history and history[0]["score_id"] == snap["score_id"], history)

    # 2. The spec's examples: 3 of 4 workouts, 7 h vs 8 h sleep, 6,000 of 8,000 steps.
    ben = create_user("Ben")
    if ben:
        log_days(ben, range(7), workouts=(1, 3, 5), sleep=7, steps=6000,
                 meal={"calories": 2200, "protein_g": 120, "carbs_g": 250, "fat_g": 67})
        s = week(ben)
        print("Ben - spec examples")
        check("workouts 75 (3 of 4)", s["workouts"] == 75, s)
        check("sleep 88 (7 h of 8 h)", s["sleep"] == 88, s)
        check("activity 75 (6,000 of 8,000 steps)", s["activity"] == 75, s)
        check("nutrition 90 (10% over calories, 80% of protein)", s["nutrition"] == 90, s)
        check("overall 82 = 75x.30 + 90x.25 + 87.5x.25 + 75x.20", s["overall_score"] == 82, s)
        users.append(("ben", "spec examples", s))

    # 3. Only logs sleep: provisional score from one category.
    cara = create_user("Cara", fitness_goal="lose_weight", workout_frequency=3)
    if cara:
        log_days(cara, range(5), sleep=6, goals=False)
        s = week(cara)
        print("Cara - sleep only")
        check("provisional, sleep only (6 h of 8 h = 75)",
              s["provisional"] and s["available_categories"] == ["sleep"] and s["overall_score"] == 75, s)
        check("nutrition targets estimated from profile", s["categories"]["nutrition"]["targets_estimated"], s)
        users.append(("cara", "sleep only", s))

    # 4. Brand new: nothing logged, so no numerical score.
    dev = create_user("Dev", fitness_level="beginner", workout_location="home")
    if dev:
        s = week(dev)
        print("Dev - new player")
        check("no HealthScore shown", s["overall_score"] is None and s["available_categories"] == [], s)
        users.append(("dev", "new player", s))

    if users:
        print(f"\nLog in at {FRONTEND_URL} with the password in SAMPLE_PASSWORD (this script):")
        for username, label, s in users:
            score = s["overall_score"] if s["overall_score"] is not None else "--"
            print(f"  {username:6} {label:15} score {score}")


if __name__ == "__main__":
    main()
