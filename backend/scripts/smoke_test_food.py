"""Live smoke test for food logging: real spaCy model + real FoodData Central + real Supabase.

Needs backend/sql/001-006 applied, FDC_API_KEY in .env, and the sample players
(python backend/scripts/seed_sample_users.py).

Usage:
    docker compose up -d --build
    python backend/scripts/smoke_test_food.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from seed_sample_users import SAMPLE_PASSWORD  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # portion labels use ≈ / ×; Windows consoles default to cp1252

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
TODAY = date.today().isoformat()


def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(label, condition, detail=""):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        print(f"       {detail}")
        sys.exit(1)


def item(meal, name):
    return next(i for i in meal["items"] if i["ingredient_text"] == name)


def main():
    status, account = request("POST", "/auth/login", {"username": "dev", "password": SAMPLE_PASSWORD})
    check("log in as sample player 'dev'", status == 200, f"{status} {account} - run seed_sample_users.py first")
    uid = account["user_id"]
    _, before = request("GET", f"/gamification/{uid}")

    status, meal = request("POST", f"/meals/{uid}/analyze", {"text": "I had a 3-egg omelette for breakfast", "log_date": TODAY})
    check("analyze the spec's example meal", status == 200, f"{status} {meal}")
    for i in meal["items"]:
        tag = " (assumed)" if i["is_assumed"] else ""
        print(f"       {i['ingredient_text']:15} {i['portion_label'][:40]:40} {i['calories']:6.1f} kcal  <- {i['food']['description']}{tag}")
    t = meal["totals"]
    print(f"       total: {t['calories']:.0f} kcal, {t['protein_g']:.1f} g protein, {t['carbs_g']:.1f} g carbs, {t['fat_g']:.1f} g fat")
    check("3 eggs = 150 g from the text, oil and cheese assumed",
          item(meal, "egg")["grams"] == 150 and item(meal, "olive oil")["is_assumed"] and item(meal, "cheddar cheese")["is_assumed"], meal)
    check("totals close to the mockup (≈337 kcal, 23.9 g protein)",
          abs(t["calories"] - 337) < 8 and abs(t["protein_g"] - 23.9) < 2, t)
    check("saved as an estimate", meal["status"] == "estimated")

    cheese = item(meal, "cheddar cheese")
    status, adjusted = request("PATCH", f"/meals/{meal['meal_id']}/items/{cheese['meal_item_id']}", {"quantity": 40})
    check("double the cheese -> totals go up", status == 200 and adjusted["totals"]["calories"] > t["calories"] + 70, adjusted.get("totals"))

    status, unknown = request("POST", f"/meals/{uid}/analyze", {"text": "a bowl of pho", "log_date": TODAY})
    check("food not in the food list is found by FDC search", status == 200 and unknown["items"][0]["food"], unknown)
    print(f"       pho -> {unknown['items'][0]['food']['description']} (confidence {unknown['items'][0]['match_confidence']})")
    request("POST", f"/meals/{unknown['meal_id']}/discard")

    status, confirmed = request("POST", f"/meals/{meal['meal_id']}/confirm")
    check("confirm the meal", status == 200 and confirmed["status"] == "confirmed", confirmed)
    _, after = request("GET", f"/gamification/{uid}")
    check("+10 meal_logged points", after["total_points"] == before["total_points"] + 10, (before, after))
    _, hs = request("GET", f"/healthscore/{uid}?range=week&end_date={TODAY}")
    check("HealthScore sees the confirmed meal", hs["categories"]["nutrition"]["days_logged"] >= 1, hs["categories"]["nutrition"])

    status, bad = request("POST", f"/meals/{uid}/analyze", {"text": "went for a run today", "log_date": TODAY})
    check("no food in the text -> helpful 422", status == 422, f"{status} {bad}")
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
