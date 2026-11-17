"""The System's achievements: the catalog's rules, what triggers each kind, and how they're paid out."""

import re
import string
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import achievement_service
from app.achievements import ACHIEVEMENTS, BY_CODE, RARITIES, REWARDS

PROFILE = {
    "age": 25, "height_cm": 175.0, "weight_kg": 70.0, "fitness_goal": "general_fitness",
    "fitness_level": "beginner", "workout_frequency": 3, "workout_location": "gym",
}
DAY = date(2026, 11, 10)   # a Tuesday


@pytest.fixture
def uid(client):
    user_id = str(uuid4())
    assert client.put(f"/profiles/{user_id}", json=PROFILE).status_code == 200
    return user_id


def codes(response):
    return [a["code"] for a in response.json()["achievements"]]


def steps(client, uid, day, n):
    return client.put(f"/logs/{uid}/activity/{day}", json={"steps": n})


def meal(client, uid, day, kind, name):
    return client.post(f"/logs/{uid}/meals", json={"log_date": str(day), "meal_type": kind, "display_name": name,
                                                   "calories": 500, "protein_g": 20, "carbs_g": 50, "fat_g": 15})


def coins(fake_db, uid):
    return fake_db.tables["user_gamification"][uid].get("fitcoins") or 0


# --- the catalog -------------------------------------------------------------------------------

def test_there_are_forty_with_everything_they_need():
    assert len(ACHIEVEMENTS) == 40 and len(BY_CODE) == 40
    for a in ACHIEVEMENTS:
        assert a.rarity in RARITIES
        assert a.name and a.description and a.plain and len(a.lines) >= 2, a.code
        assert a.triggers, a.code
        if a.hidden:
            assert a.hint, f"{a.code} is hidden, so it needs a hint"


def test_the_ones_for_unhealthy_extremes_pay_nothing():
    for code in ("couch_defense", "running_on_fumes", "ghosted_the_gym", "rock_bottom"):
        assert BY_CODE[code].reward == (0, 0)
    assert BY_CODE["accidental_marathon"].reward == REWARDS["rare"]


def test_no_jokes_about_bodies_or_eating_less():
    banned = re.compile(r"\b(weight|fat|skinny|diet|calorie deficit|starv\w*|belly|thighs?)\b", re.I)
    for a in ACHIEVEMENTS:
        for text in (a.name, a.description, a.plain, a.hint, *a.lines):
            assert not banned.search(text), f"{a.code}: {text}"


def test_every_placeholder_is_one_its_check_fills():
    known = {"steps", "hours", "meal", "count", "minutes", "days", "score", "league"}
    for a in ACHIEVEMENTS:
        for text in (a.description, *a.lines):
            fields = {f for _, f, _, _ in string.Formatter().parse(text) if f}
            assert fields <= known, f"{a.code}: {fields - known}"


# --- triggered by logs -------------------------------------------------------------------------

def test_a_huge_step_day_is_announced_and_paid_once(client, fake_db, uid):
    first = steps(client, uid, DAY, 31000)
    marathon = next(a for a in first.json()["achievements"] if a["code"] == "accidental_marathon")
    assert marathon["name"] == "Accidental Marathon" and marathon["rarity"] == "rare"
    assert "31,000 steps" in marathon["description"]
    assert marathon["commentary"] in [line.format(steps="31,000") for line in BY_CODE["accidental_marathon"].lines]
    assert marathon["reward"]["fitcoins"] == 40 and marathon["reward"]["xp"] == 60
    balance = coins(fake_db, uid)
    assert "accidental_marathon" not in codes(steps(client, uid, DAY + timedelta(days=1), 32000))
    assert coins(fake_db, uid) == balance                     # no second payout (the new log's own coins aside)


def test_a_couch_day_gets_a_line_but_no_reward(client, fake_db, uid):
    response = steps(client, uid, DAY, 400)
    couch = next(a for a in response.json()["achievements"] if a["code"] == "couch_defense")
    assert couch["rewarded"] is False and couch["reward"] is None


def test_step_counts_with_a_pattern(client, uid):
    assert "palindrome_pedestrian" in codes(steps(client, uid, DAY, 12321))
    assert "suspiciously_round" in codes(steps(client, uid, DAY + timedelta(days=1), 9000))


def test_a_long_night_and_a_short_one(client, uid):
    long = client.put(f"/logs/{uid}/sleep/{DAY}", json={"hours_slept": 10.5, "sleep_quality": 1}).json()["achievements"]
    by_code = {a["code"]: a for a in long}
    assert "10.5 hours" in by_code["sleep_of_the_dead"]["description"]
    assert "haunted_mattress" in by_code
    short = client.put(f"/logs/{uid}/sleep/{DAY + timedelta(days=1)}", json={"hours_slept": 3}).json()["achievements"]
    assert [a["code"] for a in short] == ["running_on_fumes"] and short[0]["reward"] is None


def test_snacks_and_the_same_dinner_every_night(client, uid):
    for _ in range(4):
        meal(client, uid, DAY, "snack", "Trail mix")
    fifth = meal(client, uid, DAY, "snack", "Trail mix").json()["achievements"]
    snack = next(a for a in fifth if a["code"] == "snack_attack")
    assert "5 snacks" in snack["description"]
    for back in range(4, 0, -1):
        assert "creature_of_habit" not in codes(meal(client, uid, DAY + timedelta(days=5 - back), "dinner", "Chicken rice bowl"))
    habit = meal(client, uid, DAY + timedelta(days=5), "dinner", "chicken rice bowl").json()["achievements"]
    found = next(a for a in habit if a["code"] == "creature_of_habit")   # names match regardless of capitals
    assert "chicken rice bowl" in found["description"]


def test_breakfast_foods_at_dinner_and_dessert_at_breakfast(client, uid):
    assert "breakfast_for_dinner" in codes(meal(client, uid, DAY, "dinner", "Blueberry pancakes"))
    assert "dessert_first" in codes(meal(client, uid, DAY, "breakfast", "Chocolate cake"))


def test_two_workouts_in_a_day_and_three_skips(client, uid):
    log = lambda day, status, minutes=None: client.post(f"/logs/{uid}/workouts", json={  # noqa: E731
        "workout_date": str(day), "completion_status": status, "duration_minutes": minutes})
    assert "double_feature" not in codes(log(DAY, "completed", 45))
    second = codes(log(DAY, "completed", 8))
    assert "double_feature" in second and "blink_workout" in second
    for i in (1, 2):
        assert "ghosted_the_gym" not in codes(log(DAY + timedelta(days=i), "skipped"))
    assert "ghosted_the_gym" in codes(log(DAY + timedelta(days=3), "skipped"))


def test_coming_back_after_a_quiet_week(client, uid):
    steps(client, uid, DAY, 5000)
    back = steps(client, uid, DAY + timedelta(days=9), 5000).json()["achievements"]
    found = next(a for a in back if a["code"] == "back_from_the_dead")
    assert "8 days" in found["description"]


# --- league, shop and the avatar -----------------------------------------------------------------

def test_three_avatar_changes_in_a_day_is_an_identity_crisis(client, uid):
    body = lambda b: client.put(f"/gamification/{uid}/avatar-body", json={"body": b}).json()["achievements"]  # noqa: E731
    assert body("female") == [] and body("female") == []     # picking the same body again isn't a change
    assert body("male") == []
    crisis = body("female")
    assert [a["code"] for a in crisis] == ["identity_crisis"] and "3 times" in crisis[0]["description"]


def test_the_demo_button_always_looks_like_the_first_time_but_pays_once(client, fake_db, uid):
    first = client.post(f"/gamification/{uid}/achievements/demo").json()["achievements"]
    assert first[0]["code"] == "identity_crisis" and first[0]["reward"]["fitcoins"] == 5 and first[0]["paid"] is True
    again = client.post(f"/gamification/{uid}/achievements/demo").json()["achievements"]
    assert again[0]["reward"] == {"xp": 10, "fitcoins": 5} and again[0]["paid"] is False and "replay" not in again[0]
    assert coins(fake_db, uid) == 5


def test_league_checks():
    ctx = SimpleNamespace(extra={"tier": 3, "previous_tier": 2, "league": "Silver Premium", "position": 1, "members": 12})
    assert BY_CODE["promoted"].check(ctx) == {"league": "Silver Premium"}
    assert BY_CODE["relegated"].check(ctx) is None
    assert BY_CODE["king_of_the_hill"].check(ctx) == {}
    assert BY_CODE["final_boss"].check(ctx) is None
    assert BY_CODE["promoted"].check(SimpleNamespace(extra={"tier": 0, "previous_tier": None})) is None


def test_healthscore_checks_need_a_complete_day():
    day = lambda score, provisional=False: SimpleNamespace(  # noqa: E731
        day_score=lambda: {"overall_score": score, "provisional": provisional})
    assert BY_CODE["perfect_day"].check(day(100)) == {}
    assert BY_CODE["perfect_day"].check(day(100, provisional=True)) is None
    assert BY_CODE["rock_bottom"].check(day(22)) == {"score": 22}
    assert BY_CODE["perfectly_balanced"].check(day(50)) == {}


# --- the list on the League tab ------------------------------------------------------------------

def test_the_list_shows_earned_ones_in_full_and_hides_the_rest(client, uid):
    steps(client, uid, DAY, 12321)
    data = client.get(f"/gamification/{uid}/achievements").json()
    assert data["total"] == 40 and data["earned"] >= 1
    first = data["items"][0]
    assert first["earned"] and first["commentary"] and "12,321" in (first["description"] + first["commentary"])
    secret = next(i for i in data["items"] if not i["earned"] and i["hidden"])
    assert secret["name"] == "???" and secret["hint"] and "commentary" not in secret
    goal = next(i for i in data["items"] if not i["earned"] and not i["hidden"])
    assert goal["name"] != "???" and goal["plain"]
    assert sum(r["total"] for r in data["by_rarity"].values()) == 40
    assert "achievements" not in data          # so the frontend doesn't announce the list


def test_a_broken_award_never_breaks_the_log(client, fake_db, uid, monkeypatch):
    original = fake_db.rpc

    def failing(name, params):
        if name == "award_achievement":
            raise RuntimeError("function award_achievement does not exist")
        return original(name, params)
    monkeypatch.setattr(fake_db, "rpc", failing)
    response = steps(client, uid, DAY, 31000)
    assert response.status_code == 200 and response.json()["achievements"] == []


def test_each_player_hears_the_same_line_every_time():
    a = BY_CODE["plan_what_plan"]
    assert achievement_service._commentary(a, "player-1") == achievement_service._commentary(a, "player-1")
