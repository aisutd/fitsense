"""Create 200 test players (tester001 ... tester200) in Supabase, with varied profiles and logs.

Everyone on the team who runs the app against the same Supabase project (same SUPABASE_URL in .env)
can log in as any of them with the password in SAMPLE_PASSWORD (seed_sample_users.py).

Usage:
    docker compose up -d --build
    python backend/scripts/seed_test_users.py              # all 200
    python backend/scripts/seed_test_users.py --count 20   # tester001 ... tester020

Profiles and habits are generated from the username, so every run produces the same players.
Re-running skips accounts that already exist (their data is left alone) and checks every login.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import seed_sample_users  # noqa: E402
from seed_sample_users import BASE_URL, SAMPLE_PASSWORD  # noqa: E402

TODAY = date.today()
WORKERS = 8


def request(method, path, body=None, attempts=4):
    """seed_sample_users.request, retrying the occasional dropped Supabase connection (a 5xx or bad reply)."""
    for attempt in range(attempts):
        try:
            status, data = seed_sample_users.request(method, path, body)
        except (json.JSONDecodeError, urllib.error.URLError, ConnectionError) as e:
            status, data = 599, str(e)
        if status < 500 or attempt == attempts - 1:
            return status, data
        time.sleep(0.5 * 2 ** attempt)

FIRST_NAMES = [
    "Aaliyah", "Aarav", "Abby", "Adam", "Aiden", "Aisha", "Alex", "Amara", "Amir", "Ana", "Andre", "Anika", "Arjun",
    "Ben", "Bianca", "Brandon", "Caleb", "Camila", "Carlos", "Chloe", "Chris", "Daniel", "Daniela", "David", "Diego",
    "Elena", "Eli", "Emily", "Emma", "Ethan", "Fatima", "Gabriel", "Grace", "Hana", "Hannah", "Hector", "Isaac",
    "Isabella", "Jack", "Jada", "Jamal", "James", "Jasmine", "Javier", "Jin", "Jordan", "Jose", "Julia", "Kai",
    "Kayla", "Kenji", "Kevin", "Laila", "Leah", "Leo", "Liam", "Lily", "Lucas", "Luis", "Maya", "Mei", "Mia",
    "Michael", "Mohammed", "Nadia", "Naomi", "Nathan", "Nia", "Noah", "Olivia", "Omar", "Priya", "Rafael", "Riya",
    "Rohan", "Ryan", "Sam", "Samira", "Sara", "Sofia", "Tariq", "Tyler", "Valeria", "Victor", "Wei", "Yara",
    "Yusuf", "Zara", "Zoe",
]
GOALS = ["lose_weight", "build_muscle", "improve_endurance", "general_fitness", "increase_flexibility"]
LEVELS = ["beginner", "intermediate", "advanced"]
LOCATIONS = ["gym", "home", "outdoors", "mixed"]
PREFERENCES = ["strength", "cardio", "hiit", "yoga", "pilates", "sports", "calisthenics"]

# Habits, so HealthScores range from "--" to 100. Weights add up to 1.
PERSONAS = [
    ("on track", 0.25),        # most planned workouts, good sleep, steps and meals
    ("mixed", 0.25),           # some of everything, some days missed
    ("struggling", 0.15),      # few workouts, short sleep, low steps
    ("partial logger", 0.15),  # only logs one or two categories (provisional score)
    ("lapsed", 0.10),          # logged last week, nothing this week
    ("new player", 0.10),      # nothing logged yet
]


def username(n: int) -> str:
    return f"tester{n:03d}"


def make_profile(rng: random.Random) -> dict:
    height = rng.gauss(171, 10)
    bmi = rng.uniform(19, 31)
    return {
        "name": rng.choice(FIRST_NAMES),
        "age": rng.randint(18, 60),
        "height_cm": round(min(max(height, 150), 200), 1),
        "weight_kg": round(bmi * (height / 100) ** 2, 1),
        "fitness_goal": rng.choice(GOALS),
        "fitness_level": rng.choices(LEVELS, weights=[0.45, 0.4, 0.15])[0],
        "workout_frequency": rng.randint(2, 6),
        "workout_location": rng.choice(LOCATIONS),
        "workout_preferences": rng.sample(PREFERENCES, rng.randint(1, 3)),
    }


def targets(profile: dict) -> dict:
    calories = round(profile["weight_kg"] * 30 / 50) * 50
    protein = round(profile["weight_kg"] * 1.6)
    fat = round(calories * 0.28 / 9)
    carbs = max(round((calories - protein * 4 - fat * 9) / 4), 50)
    return {"calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat}


def plan_logs(rng: random.Random, persona: str, profile: dict) -> list[tuple[str, str, dict]]:
    """(method, path suffix, body) for the last 14 days of logs."""
    target = targets(profile)
    days_this_week, days_last_week = range(0, 7), range(7, 14)
    # (chance a workout day is done, sleep hours range, steps range, calorie error, chance a day is logged)
    habits = {
        "on track":   (0.95, (7.3, 8.8), (8000, 13000), 0.08, 0.95),
        "mixed":      (0.6, (6.3, 8.2), (5000, 10000), 0.2, 0.7),
        "struggling": (0.3, (4.8, 6.6), (2000, 6000), 0.35, 0.6),
        "partial logger": (0.7, (6.0, 8.5), (4000, 11000), 0.15, 0.8),
        "lapsed":     (0.7, (6.5, 8.5), (5000, 11000), 0.15, 0.8),
    }[persona]
    workout_rate, sleep_range, steps_range, cal_error, log_rate = habits
    days = days_last_week if persona == "lapsed" else range(0, 14)
    categories = {"workouts", "sleep", "activity", "nutrition"}
    if persona == "partial logger":
        categories = set(rng.sample(sorted(categories), rng.randint(1, 2)))

    logs = []
    if "nutrition" in categories and rng.random() < 0.7:
        logs.append(("PUT", "goals", {"nutrition": {"daily_calorie_target": target["calories"],
                                                    "protein_target_g": target["protein_g"],
                                                    "carbs_target_g": target["carbs_g"], "fat_target_g": target["fat_g"]},
                                      "sleep_target_hours": rng.choice([7, 7.5, 8, 8, 8.5]),
                                      "daily_steps": rng.choice([6000, 8000, 8000, 10000])}))
    for week in (days_this_week, days_last_week):
        if "workouts" in categories:
            logged_days = [d for d in week if d in days]
            for d in sorted(rng.sample(logged_days, min(profile["workout_frequency"], len(logged_days)))):
                done = rng.random() < workout_rate
                logs.append(("POST", "workouts", {"workout_date": iso(d),
                                                  "completion_status": "completed" if done else rng.choice(["partial", "skipped"]),
                                                  "duration_minutes": rng.choice([20, 30, 45, 45, 60, 75]) if done else None}))
    for d in days:
        if rng.random() > log_rate:
            continue
        if "sleep" in categories:
            logs.append(("PUT", f"sleep/{iso(d)}", {"hours_slept": round(rng.uniform(*sleep_range) * 4) / 4,
                                                    "sleep_quality": rng.randint(2, 5)}))
        if "activity" in categories:
            logs.append(("PUT", f"activity/{iso(d)}", {"steps": rng.randrange(*steps_range, 50)}))
        if "nutrition" in categories:
            f = 1 + rng.uniform(-cal_error, cal_error)
            logs.append(("POST", "meals", {"log_date": iso(d), "meal_type": "dinner", "display_name": "Day's meals",
                                           "calories": round(target["calories"] * f),
                                           "protein_g": round(target["protein_g"] * rng.uniform(0.6, 1.1), 1),
                                           "carbs_g": round(target["carbs_g"] * f, 1),
                                           "fat_g": round(target["fat_g"] * f, 1)}))
    return logs


def iso(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def seed_one(n: int) -> tuple[str, str]:
    """Returns (username, outcome)."""
    name = username(n)
    rng = random.Random(f"fitsense-{name}")
    persona = rng.choices([p for p, _ in PERSONAS], weights=[w for _, w in PERSONAS])[0]
    profile = make_profile(rng)

    status, account = request("POST", "/auth/signup", {"username": name, "password": SAMPLE_PASSWORD})
    if status == 409:
        # finished earlier unless an interrupted run left it without a profile
        status, account = request("POST", "/auth/login", {"username": name, "password": SAMPLE_PASSWORD})
        if status != 200 or account.get("has_profile"):
            return name, "exists"
    elif status != 201:
        return name, f"signup failed: {status} {account}"
    uid = account["user_id"]
    status, body = request("PUT", f"/profiles/{uid}", profile)
    if status != 200:
        return name, f"profile failed: {status} {body}"
    if persona != "new player":
        for method, path, payload in plan_logs(rng, persona, profile):
            url = f"/goals/{uid}" if path == "goals" else f"/logs/{uid}/{path}"
            status, body = request(method, url, payload)
            if status not in (200, 201):
                return name, f"{method} {url} failed: {status} {body}"
    return name, f"created ({persona})"


def check_login(n: int) -> tuple[str, bool, int | None]:
    name = username(n)
    status, account = request("POST", "/auth/login", {"username": name, "password": SAMPLE_PASSWORD})
    if status != 200 or not account.get("has_profile"):
        return name, False, None
    _, score = request("GET", f"/healthscore/{account['user_id']}?range=week&end_date={TODAY}")
    return name, True, (score or {}).get("overall_score")


def main() -> int:
    ap = argparse.ArgumentParser(description="Create test players tester001 ... testerNNN")
    ap.add_argument("--count", type=int, default=200)
    args = ap.parse_args()
    numbers = range(1, args.count + 1)
    if request("GET", "/health", attempts=1)[0] != 200:
        print(f"Can't reach the backend at {BASE_URL}. Start it with: docker compose up -d --build", file=sys.stderr)
        return 1
    print(f"Seeding {args.count} test players on {BASE_URL} (today = {TODAY}) ...")

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(seed_one, numbers))
    failed = [(u, r) for u, r in results if not (r == "exists" or r.startswith("created"))]
    created = [r for _, r in results if r.startswith("created")]
    print(f"  created {len(created)}, already existed {sum(r == 'exists' for _, r in results)}, failed {len(failed)}")
    for persona, _ in PERSONAS:
        count = sum(r == f"created ({persona})" for r in created)
        if count:
            print(f"    {persona:15} {count}")
    for u, r in failed[:10]:
        print(f"  [FAIL] {u}: {r}")

    print("Checking every login ...")
    with ThreadPoolExecutor(WORKERS) as pool:
        logins = list(pool.map(check_login, numbers))
    bad = [u for u, ok, _ in logins if not ok]
    scores = [s for _, ok, s in logins if ok and s is not None]
    print(f"  {len(logins) - len(bad)} of {len(logins)} log in and have a profile; "
          f"{len(scores)} have a HealthScore this week (range {min(scores, default='-')}-{max(scores, default='-')})")
    if bad:
        print("  [FAIL] can't log in: " + ", ".join(bad[:20]))
    print(f"\nLog in as {username(1)} ... {username(args.count)} with the password in SAMPLE_PASSWORD (seed_sample_users.py).")
    return 1 if failed or bad else 0


if __name__ == "__main__":
    sys.exit(main())
