"""League standings include every player with a season HealthScore, not just those who opened it."""

from datetime import date
from uuid import uuid4

import pytest

PROFILE = {"name": "P", "age": 25, "height_cm": 180.0, "weight_kg": 80.0, "fitness_goal": "general_fitness",
           "fitness_level": "intermediate", "workout_frequency": 4, "workout_location": "gym"}
TODAY = date.today().isoformat()


def player(client, name, steps=None):
    uid = str(uuid4())
    assert client.put(f"/profiles/{uid}", json={**PROFILE, "name": name}).status_code == 200
    if steps is not None:
        assert client.put(f"/logs/{uid}/activity/{TODAY}", json={"steps": steps}).status_code == 200
    return uid


@pytest.fixture
def league(client):
    """Six players who logged steps today (more steps = better score) and one who logged nothing."""
    ids = {name: player(client, name, steps) for name, steps in
           [("Ana", 7600), ("Ben", 7000), ("Cy", 6000), ("Di", 4000), ("Ed", 2000), ("Flo", 1000)]}
    ids["Gus"] = player(client, "Gus")
    return ids


def test_everyone_with_a_score_is_ranked(client, league):
    board = client.get(f"/gamification/{league['Cy']}/league").json()
    assert board["league"]["members"] == 6 and board["league"]["position"] == 3
    assert [p["name"] for p in board["podium"]] == ["Ana", "Ben", "Cy", "Di", "Ed"]
    assert board["podium"][2]["is_current_user"] is True


def test_movement_zones(client, league):
    assert client.get(f"/gamification/{league['Ana']}/league").json()["league"]["movement"] == "promotion zone"
    # Bronze is the lowest league, so nobody is demoted from it
    assert client.get(f"/gamification/{league['Flo']}/league").json()["league"]["movement"] == "holding position"


def test_player_without_a_score_sees_the_board(client, league):
    board = client.get(f"/gamification/{league['Gus']}/league").json()
    assert board["league"]["position"] is None and board["league"]["movement"] == "needs a HealthScore"
    assert len(board["podium"]) == 5


def test_standings_are_cached(client, league, fake_db):
    client.get(f"/gamification/{league['Ana']}/league")
    stamps = {r["updated_at"] for r in fake_db.tables["league_season_scores"].values()}
    client.put(f"/logs/{league['Flo']}/activity/{TODAY}", json={"steps": 20000})
    board = client.get(f"/gamification/{league['Flo']}/league").json()
    assert {r["updated_at"] for r in fake_db.tables["league_season_scores"].values()} == stamps
    assert board["league"]["position"] == 6          # refreshed within 10 minutes, not on every view


def test_unknown_player(client):
    assert client.get(f"/gamification/{uuid4()}/league").status_code == 404


def test_stale_standings_refresh_after_the_response(client, league, fake_db):
    client.get(f"/gamification/{league['Ana']}/league")
    for row in fake_db.tables["league_season_scores"].values():
        row["updated_at"] = "2000-01-01T00:00:00+00:00"          # long out of date
    client.put(f"/logs/{league['Flo']}/activity/{TODAY}", json={"steps": 20000})
    first = client.get(f"/gamification/{league['Flo']}/league").json()
    assert first["league"]["position"] == 6                      # old standings, answered straight away
    assert client.get(f"/gamification/{league['Flo']}/league").json()["league"]["position"] == 1


def test_board_has_the_banner_details(client, league):
    board = client.get(f"/gamification/{league['Cy']}/league").json()
    assert board["player"] == {"name": "Cy", "fitness_level": "intermediate", "avatar_body": "male"}
    assert isinstance(board["league"]["season_health_score"], int)
    assert "hidden_score" not in str(board)                     # the ranking score stays private
    assert board["podium"][0]["fitness_level"] == "intermediate"
    no_score = client.get(f"/gamification/{league['Gus']}/league").json()
    assert no_score["league"]["season_health_score"] is None


def test_avatar_body(client, league):
    assert client.put(f"/gamification/{league['Ana']}/avatar-body", json={"body": "female"}).json() == {"avatar_body": "female"}
    assert client.get(f"/gamification/{league['Ana']}/league").json()["player"]["avatar_body"] == "female"
    assert client.put(f"/gamification/{league['Ana']}/avatar-body", json={"body": "robot"}).status_code == 422
    assert client.put(f"/gamification/{uuid4()}/avatar-body", json={"body": "male"}).status_code == 404


def test_the_whole_league_is_on_the_board(client, league):
    board = client.get(f"/gamification/{league['Cy']}/league").json()
    standings = board["standings"]
    assert [row["name"] for row in standings] == ["Ana", "Ben", "Cy", "Di", "Ed", "Flo"]
    assert [row["is_current_user"] for row in standings] == [False, False, True, False, False, False]
    # the top fifth, rounded up (2 of 6), is promoted; nobody drops out of Bronze, the lowest league
    assert [row["zone"] for row in standings] == ["promotion", "promotion", None, None, None, None]
    assert not any("score" in key for row in standings for key in row)   # the ranking score stays hidden
    assert board["leagues"][0] == "Bronze" and board["podium"][0]["name"] == "Ana"
