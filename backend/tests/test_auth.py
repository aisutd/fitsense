import pytest

from app.passwords import hash_password, verify_password

PROFILE = {
    "age": 21, "height_cm": 175.0, "weight_kg": 70.0, "fitness_goal": "build_muscle",
    "fitness_level": "beginner", "workout_frequency": 4, "workout_location": "gym",
}
PASSWORD = "correct-horse-1"


def signup(client, username="ava", password=PASSWORD):
    return client.post("/auth/signup", json={"username": username, "password": password})


def login(client, username="ava", password=PASSWORD):
    return client.post("/auth/login", json={"username": username, "password": password})


# --- password hashing ----------------------------------------------------------------

def test_hash_round_trip_and_salted():
    h1, h2 = hash_password(PASSWORD), hash_password(PASSWORD)
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password(PASSWORD, h1) and verify_password(PASSWORD, h2)
    assert not verify_password("wrong-password", h1)


@pytest.mark.parametrize("stored", ["", "plaintext", "bcrypt$1$2$3$x$y", "scrypt$x$8$1$abc$def"])
def test_malformed_hashes_never_verify(stored):
    assert verify_password(PASSWORD, stored) is False


# --- signup & login ------------------------------------------------------------------

def test_signup_stores_hash_not_password(client, fake_db):
    res = signup(client, "Ava")
    assert res.status_code == 201
    body = res.json()
    assert body["username"] == "ava" and body["has_profile"] is False
    stored = fake_db.tables["accounts"][body["user_id"]]
    assert PASSWORD not in stored["password_hash"]
    assert verify_password(PASSWORD, stored["password_hash"])


def test_signup_then_onboarding_then_login(client):
    user_id = signup(client).json()["user_id"]
    assert login(client).json() == {"user_id": user_id, "username": "ava", "has_profile": False}

    assert client.put(f"/profiles/{user_id}", json=PROFILE).status_code == 200
    res = login(client)
    assert res.status_code == 200 and res.json()["has_profile"] is True
    assert client.get(f"/healthscore/{user_id}").status_code == 200


def test_login_is_case_insensitive_and_records_time(client, fake_db):
    user_id = signup(client, "Ava").json()["user_id"]
    assert login(client, "AVA").status_code == 200
    assert fake_db.tables["accounts"][user_id]["last_login_at"]


def test_duplicate_username_rejected_any_case(client):
    assert signup(client, "ava").status_code == 201
    res = signup(client, "AVA", "another-password")
    assert res.status_code == 409 and res.json()["detail"] == "That username is taken"


def test_wrong_password_and_unknown_user_look_the_same(client):
    signup(client)
    wrong = login(client, password="nope-nope-nope")
    unknown = login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Wrong username or password"}


@pytest.mark.parametrize(
    "body",
    [
        {"username": "ab", "password": PASSWORD},
        {"username": "has space", "password": PASSWORD},
        {"username": "x" * 31, "password": PASSWORD},
        {"username": "ava", "password": "short"},
        {"username": "ava", "password": "x" * 129},
        {"username": "ava"},
        {"username": "ava", "password": PASSWORD, "is_admin": True},
    ],
)
def test_invalid_signup_rejected(client, body):
    assert client.post("/auth/signup", json=body).status_code == 422


def test_login_requires_both_fields(client):
    assert client.post("/auth/login", json={"username": "ava"}).status_code == 422
