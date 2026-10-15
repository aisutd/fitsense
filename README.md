# FitSense

## Description

FitSense is an AI-powered personalized fitness and wellness platform. It uses goals, workout history, activity, feedback, and recovery data to recommend workouts, forecast progress, calculate an interpretable HealthScore, and power adaptive gamification.

## Planned Technologies

- Python, JavaScript/TypeScript, and SQL
- React or Streamlit with Plotly
- FastAPI, Pandas, and NumPy
- Recommendation systems, forecasting, NLP, PostgreSQL, and Supabase

## Docker Setup

Make sure Docker Desktop is installed and running.

```bash
docker compose up -d
docker compose down
docker compose ps
```

This is a generic starter configuration. The team can add project-specific dependencies and startup commands later.

## Backend

### Setup

1. Copy `.env.example` to `.env` in the repo root and fill in `SUPABASE_URL` and `SUPABASE_KEY`.
   Use the **secret** (service_role) key: every table has row level security enabled, so the publishable/anon key can't read or write them.
2. In the Supabase dashboard, open the **SQL Editor** and run each file in `backend/sql/` in order. Each one is safe to run again.
   - `001_create_profiles.sql`: the `profiles` table
   - `002_data_model.sql`: the rest of the FitSense data model (workouts, nutrition, sleep, activity, HealthScore, forecasts, gamification, food logging, achievements)
   - `003_gamification_points.sql`: the `xp_events` points history and the `award_points` function
3. Run `docker compose up -d --build`. The API is at http://localhost:8000, and interactive docs are at http://localhost:8000/docs.

### Profile endpoints

| Method | Path | Description |
|---|---|---|
| `PUT` | `/profiles/{user_id}` | Create or replace a user's profile. Returns the stored profile. |
| `GET` | `/profiles/{user_id}` | Get a user's profile, or `404` if none exists. |

`user_id` is a UUID, which the frontend generates for now (`crypto.randomUUID()`). Height and weight are **metric** (cm and kg). Invalid data is rejected with `422`.

Example request body:

```json
{
  "name": "Alex",
  "age": 21,
  "height_cm": 175.3,
  "weight_kg": 70.2,
  "fitness_goal": "build_muscle",
  "fitness_level": "beginner",
  "workout_frequency": 4,
  "workout_location": "gym",
  "workout_preferences": ["strength", "cardio"]
}
```

| Field | Allowed values |
|---|---|
| `name` | optional, 1–80 characters |
| `age` | 13–100 |
| `height_cm` | 100–250 |
| `weight_kg` | 30–300 |
| `fitness_goal` | `lose_weight`, `build_muscle`, `improve_endurance`, `general_fitness`, `increase_flexibility` |
| `fitness_level` | `beginner`, `intermediate`, `advanced` |
| `workout_frequency` | 1–7 (days per week) |
| `workout_location` | `home`, `gym`, `outdoors`, `mixed` |
| `workout_preferences` | optional list of `strength`, `cardio`, `hiit`, `yoga`, `pilates`, `sports`, `calisthenics` |

Saving a profile also copies the workout fields into `user_preferences` (`workout_days_per_week`, `workout_location`, `preferred_workout_types`).

### Gamification endpoints

Users earn points for actions. The backend decides how many points each action is worth, so clients can't send their own amounts. Point values and level thresholds live in `backend/app/gamification.py`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/gamification/{user_id}/points` | Add points for an action. Body: `{"action": "workout_completed", "source_id": "<optional>"}` |
| `GET` | `/gamification/{user_id}` | Total points, level, and progress toward the next level |
| `GET` | `/gamification/{user_id}/history` | Recent point awards, newest first (`?limit=` 1–100, default 20) |
| `GET` | `/gamification/actions` | Every action and its point value |
| `GET` | `/gamification/levels` | Minimum points for each level |

| Action | Points |
|---|---|
| `onboarding_completed` | 100 |
| `workout_completed` | 50 |
| `workout_partial` | 20 |
| `meal_logged` | 10 |
| `sleep_logged` | 10 |
| `daily_goals_met` | 25 |
| `streak_7_days` | 100 |

| Level | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Min points | 0 | 200 | 500 | 1,000 | 1,750 | 2,750 | 4,000 | 5,500 | 7,500 | 10,000 |

Example: a user at 200 points completes a workout, so `POST {"action": "workout_completed"}` takes them to 250 points, which is level 2.

- **`source_id`** is optional. Pass the ID of what earned the points (e.g. a workout log ID); the same source is only rewarded once per action, so retries can't double-count. The response then has `"awarded": false`.
- **Response** includes `points_awarded`, `total_points`, `level`, `previous_level`, `leveled_up`, `next_level_points`, `points_to_next_level` and `progress_percent`.
- Points are stored in `user_gamification.total_xp` (running total) and `xp_events` (history). The `award_points` database function updates both in one transaction, so simultaneous awards can't lose points.
- Unknown users get `404`; unknown actions get `422`.

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Supabase needed
python scripts/smoke_test_profiles.py         # live tests against the running backend + Supabase
python scripts/smoke_test_gamification.py
```
