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
   - `004_healthscore.sql`: HealthScore weights (30/25/25/20) and the workout/macro/activity goal columns it needs
   - `005_accounts.sql`: username/password accounts for the testing login
   - `006_food_logging.sql`: FoodData Central search cache and the meal-review fields on `meal_items`
   - `007_food_search.sql`: search index and `search_fdc_foods` function for the local USDA food copy
3. Run `docker compose up -d --build`. The API is at http://localhost:8000, and interactive docs are at http://localhost:8000/docs.
4. Load the USDA food data (once per Supabase project; about 30 seconds):
   `docker compose run --rm backend python -m app.food.fdc_import`

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

### HealthScore

An overall 0–100 score from four categories: **workouts 30%, nutrition 25%, sleep 25%, activity 20%** (weights come from the newest `health_score_config` row). The calculation is in `backend/app/healthscore.py` as reusable functions, one per category.

| Category | Score |
|---|---|
| Workouts | completed ÷ scheduled × 100, capped at 100 (partial = half). Scheduled = days per week from the newest workout plan, else onboarding, scaled to the window. |
| Nutrition | how closely daily totals from **confirmed meals** match the targets (calories 40%, protein 30%, carbs 15%, fat 15%). Needs meals on 3+ days. Without a nutrition goal, targets are estimated from the profile. |
| Sleep | closeness to the sleep target (default 8 h): 7 h → 88 |
| Activity | min(100, steps ÷ step target × 100), default 8,000 steps; active minutes (default 30) when no steps are logged |

A category without enough data is left out and the overall score is marked `provisional`; with no data at all, `overall_score` is `null`. HealthScore is a motivational wellness metric, not a medical assessment.

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthscore/{user_id}?range=week\|last-week\|month&end_date=YYYY-MM-DD` | Calculate the score (last 7 days, the 7 before that, or last 30 days) |
| `POST` | `/healthscore/{user_id}/snapshots` | Calculate and save to `health_scores` |
| `GET` | `/healthscore/{user_id}/history` | Saved scores, newest first |
| `POST` | `/logs/{user_id}/workouts` | Log a workout (`completed`, `partial`, `skipped`) |
| `PUT` | `/logs/{user_id}/sleep/{date}` | Log (or replace) a night's sleep |
| `PUT` | `/logs/{user_id}/activity/{date}` | Log (or replace) a day's steps / active minutes |
| `POST` | `/logs/{user_id}/meals` | Store a confirmed meal's nutrition (from the food-logging pipeline) |
| `GET` / `PUT` | `/goals/{user_id}` | Current targets / set nutrition, sleep, step and active-minute goals |

### Food logging

Players either **type a food and pick it** from search-as-you-type suggestions, or **describe a meal** in plain text
and the backend works out the ingredients. Either way nutrition comes from **USDA FoodData Central** (FDC) - the language
model only finds foods and amounts.

A copy of FDC lives in Supabase (`fdc_foods` / `fdc_food_portions`, about 13,500 foods from FNDDS, SR Legacy and
Foundation), loaded by `python -m app.food.fdc_import` from USDA's public downloads. Search runs in Postgres (word prefixes
and typo-tolerant trigram matching), so suggestions take ~0.1 s and the app makes no FDC API calls.

```
"I had a 3-egg omelette for breakfast"
  -> spaCy food model finds [3]-[egg] [omelette]         (backend/app/food/parser.py, trained in backend/ml/food_ner)
  -> recipe: omelette = eggs + 1 tsp oil (assumed) + 20 g cheddar (assumed)   (app/food/data/recipes.json)
  -> each food -> FDC id: ~200 common foods are pinned (app/food/data/foods.json); others are searched and ranked
  -> grams from FDC portions ("1 large egg = 50 g"), nutrients = per-100 g value x grams / 100
  -> saved as an *estimated* meal; the player adjusts amounts / swaps foods, then confirms
```

| Method | Path | Description |
|---|---|---|
| `GET` | `/foods/suggest?q=` | Search-as-you-type: foods from our list first, then USDA matches (local copy only) |
| `POST` | `/meals/{user_id}/start` | `{"log_date", "meal_type"?, "items": [{"fdc_id", "quantity"?, "unit"?}]}` -> estimated meal from picked foods |
| `POST` | `/meals/{user_id}/analyze` | `{"text", "log_date", "meal_type"?}` -> estimated meal with ingredients and totals |
| `GET` | `/meals?user_id=&log_date=` | A user's meals for a day |
| `GET` | `/meals/{meal_id}` | One meal |
| `PATCH` | `/meals/{meal_id}/items/{item_id}` | Change `quantity` / `unit`, or swap to another `fdc_id` |
| `POST` / `DELETE` | `/meals/{meal_id}/items[/{item_id}]` | Add (`{"text"}` typed, or `{"fdc_id"}` picked) or remove an ingredient |
| `POST` | `/meals/{meal_id}/confirm` | Counts toward the HealthScore and awards `meal_logged` points |
| `POST` | `/meals/{meal_id}/discard` | Throw the estimate away |
| `GET` | `/foods/search?q=` | Search foods (ranked) to swap an ingredient |

- `FDC_API_KEY` is optional: with it, a food missing from the local copy is fetched from the FDC API (and cached);
  without it those requests return `503` asking you to run the import.
- When USDA publishes a new FNDDS or Foundation release, update `DATASETS` in `backend/app/food/fdc_import.py` and re-run it.
- Ingredients added by a recipe are marked `is_assumed`; weak matches or guessed amounts are marked `needs_review`.
- The food model's training data, evaluation and retraining steps are in `backend/ml/food_ner/README.md`.

### Testing login

`POST /auth/signup` and `POST /auth/login` take `{"username", "password"}` and return `{"user_id", "username", "has_profile"}`. Passwords are stored as salted scrypt hashes in `accounts`. The account's `user_id` is also the profile's id.

This is for testing only: there are no sessions yet, and the other endpoints don't check who is calling.

To create sample players (`ava`, `ben`, `cara`, `dev`) with logs, run `python backend/scripts/seed_sample_users.py`; their password is `SAMPLE_PASSWORD` in that script.

**200 test players** (`tester001` ... `tester200`, same password) already exist in the team's Supabase project, so anyone
whose `.env` points at that project can log in as any of them. They have varied profiles and two weeks of logs with
different habits (on track, mixed, struggling, logs only some categories, lapsed, brand new), so HealthScores range from
none to 100. `python backend/scripts/seed_test_users.py` recreates them in another Supabase project (`--count N` for fewer);
it's safe to re-run and checks every login.

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Supabase needed
python scripts/smoke_test_profiles.py         # live tests against the running backend + Supabase
python scripts/smoke_test_gamification.py
python scripts/seed_sample_users.py           # sample players + HealthScore checks against the spec's examples
python scripts/seed_test_users.py             # 200 test players (tester001-tester200) with varied habits
python scripts/smoke_test_food.py             # food logging end to end (real model, FDC and Supabase)
python ml/food_ner/evaluate.py                # food model accuracy on the hand-written test set
```
