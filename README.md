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

Players describe a meal in plain text; the backend works out the ingredients and looks up nutrition in
**USDA FoodData Central** (FDC). Nutrition values always come from FDC - the language model only finds foods and amounts.

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
| `POST` | `/meals/{user_id}/analyze` | `{"text", "log_date", "meal_type"?}` -> estimated meal with ingredients and totals |
| `GET` | `/meals?user_id=&log_date=` | A user's meals for a day |
| `GET` | `/meals/{meal_id}` | One meal |
| `PATCH` | `/meals/{meal_id}/items/{item_id}` | Change `quantity` / `unit`, or swap to another `fdc_id` |
| `POST` / `DELETE` | `/meals/{meal_id}/items[/{item_id}]` | Add or remove an ingredient |
| `POST` | `/meals/{meal_id}/confirm` | Counts toward the HealthScore and awards `meal_logged` points |
| `POST` | `/meals/{meal_id}/discard` | Throw the estimate away |
| `GET` | `/foods/search?q=` | Search FDC (ranked, cached) to pick a food |

- Needs `FDC_API_KEY` in `.env` (free: https://fdc.nal.usda.gov/api-key-signup). FDC results are cached in Supabase for 30 days.
- Ingredients added by a recipe are marked `is_assumed`; weak matches or guessed amounts are marked `needs_review`.
- The food model's training data, evaluation and retraining steps are in `backend/ml/food_ner/README.md`.

### Testing login

`POST /auth/signup` and `POST /auth/login` take `{"username", "password"}` and return `{"user_id", "username", "has_profile"}`. Passwords are stored as salted scrypt hashes in `accounts`. The account's `user_id` is also the profile's id.

This is for testing only: there are no sessions yet, and the other endpoints don't check who is calling.

To create sample players (`ava`, `ben`, `cara`, `dev`) with logs, run `python backend/scripts/seed_sample_users.py`; their password is `SAMPLE_PASSWORD` in that script.

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Supabase needed
python scripts/smoke_test_profiles.py         # live tests against the running backend + Supabase
python scripts/smoke_test_gamification.py
python scripts/seed_sample_users.py           # sample players + HealthScore checks against the spec's examples
python scripts/smoke_test_food.py             # food logging end to end (real model, FDC and Supabase)
python ml/food_ner/evaluate.py                # food model accuracy on the hand-written test set
```

## Workout recommender and XGBoost ranker

`Fitsense-Issue-5.py` picks exercises with rules (level, equipment, goal). `exercise_ranker.py`
adds an XGBoost model that orders those exercises by how likely the user is to complete them.
The rules still decide what can be recommended; the model only changes the order.

```bash
pip install -r requirements.txt   # on macOS, XGBoost also needs: brew install libomp
python exercise_ranker.py train   # trains from Supabase and saves models/exercise_ranker.json
python Fitsense-Issue-5.py --user <user_id>
```

Training labels come from `plan_exercises` → `workout_plans` → `workout_logs`: each exercise in a
logged plan is labeled by whether the user completed that plan. Exercises are matched to
`home.json`/`gym.json` by name. Training needs at least 200 labeled rows (`--force` overrides);
until a model is saved, recommendations use the rule-based order.

`--user` prints the user's saved plan for this week, building it first if there is none
(`weekly_plan.py`). Week 1 comes from the profile; from week 2 on, the plan follows last week's
logs (`plan_id` + `day_number`): a full week progresses the dose, a missed one cuts days and
volume, and exercises on skipped days are swapped. Run `backend/sql/002_weekly_plans.sql` first.

```bash
python weekly_plan.py weekly [--dry-run]   # this week's plan for every user who has none
```

### Demo

Two seeded test users whose plan for the week of Oct 19 was adapted from their week-1 logs:

```bash
source .venv/bin/activate
python Fitsense-Issue-5.py --user f449eafd-7993-4a4b-ad52-8adb9fef3270   # Grace: completed week 1, reps 3x6 -> 3x8
python Fitsense-Issue-5.py --user bd0b181f-7375-4040-a928-de0a4e21e19d   # James: missed workouts, 5 -> 4 days
python progress_forecast.py --user f449eafd-7993-4a4b-ad52-8adb9fef3270  # Grace's forecast
```

This works through Sunday, Oct 25. After that each user gets a new plan, and since no logs are
linked to the current one it reads as all skipped and cuts them back. The demo keeps working
once the app saves `plan_id` and `day_number` with each logged workout.

## Weekly progress forecast (linear regression + XGBoost)

`progress_forecast.py` forecasts body weight, completed workouts per week, daily steps and
HealthScore 1, 4 and 12 weeks ahead. Each metric is averaged per week (Monday–Sunday, UTC; the
current, unfinished week is left out) and fit with a weighted linear regression:

- **Adapts weekly**: it is refit every week, and a week 4 weeks old counts half as much as the
  latest one, so a change in habits shows up in the next forecast.
- **Uses the profile**: the trend is pulled toward a prior from the user's preferences. Workouts
  start from `workout_frequency`; weight follows the `fitness_goal` (lose: −0.5 kg/week, the low
  end of the CDC's 0.45–0.9; build muscle: Aragon's lean-gain rate by `fitness_level`; other goals:
  no change). With little data the prior dominates; after about a month the user's own trend does.
- **Weight uses the workout forecast**: the goal's expected weight change is scaled by the share
  of planned workouts the user is forecast to complete, and capped at ±1 kg/week.
- **HealthScore comes from the HealthScore screen's own code**: each past week is scored by
  `backend/app/healthscore_repo.calculate` (the "Last 7 Days" view for that week), then the
  workouts, nutrition, sleep and activity scores are forecast separately and combined with the
  active `health_score_config` weights, exactly as the screen combines them. Categories the user
  hasn't logged are left out and the rest re-weighted, like the screen's provisional score. Each
  category is also saved to `progress_forecasts` (`health_score_workouts`, `health_score_sleep`, ...).
  Planned workout days come from the same place the HealthScore uses: the newest workout plan,
  then `user_preferences`, then onboarding.

`backend/app/healthscore.py` and `healthscore_repo.py` are copied unchanged from `main`; keep them
in sync until this branch is merged with `main`. They need `fastapi` (in `requirements.txt`).

```bash
python progress_forecast.py --user <user_id>   # print one user's forecast
python progress_forecast.py weekly --dry-run    # show how many rows the weekly run would save
python progress_forecast.py weekly              # save forecasts for every user to progress_forecasts
```

Schedule `weekly` once a week, for example Mondays at 06:00 UTC with cron:
`0 6 * * 1 cd /path/to/fitsense && .venv/bin/python progress_forecast.py weekly`. Users who already
have forecasts from this week are skipped, so extra runs add nothing. Each saved row keeps
`generated_at` and `model_version`, so past forecasts can be compared with what actually happened.
`Fitsense-Issue-5.py --user` also prints the forecast after the workout.

### XGBoost correction for the weight forecast

The linear regression draws a straight line, but real weight change plateaus and depends on
whether the person keeps training. `weight_forecast_model.py` adds an XGBoost model that learns
the baseline's error, so the final weight forecast is *linear baseline + XGBoost correction*:

- **Rows**: one per (user, week, horizon). The baseline is re-run as of each past Monday using only
  the data it had then, and the label is actual weekly weight minus the baseline's prediction.
- **Features** (`FEATURE_NAMES`): the baseline's level and slope, its goal prior, workout adherence,
  recent trend, scale noise, kg lost or gained so far, recent workouts and steps, weeks since
  sign-up, age, level, workout frequency, goal, and the horizon (1, 4 or 12 weeks).
- **Safety**: corrections are capped at 0.5 kg per week ahead (at least 1 kg), the model is only
  used once a user has 2 weeks of weigh-ins, and without a model file the baseline runs alone. The
  baseline's own numbers stay in `baseline_predictions`, and saved rows carry
  `model_version = linreg+xgb-weekly-v1` (baseline-only rows keep `linreg-weekly-v1`).

```bash
python weight_forecast_model.py evaluate             # held-out MAE, baseline vs baseline + XGBoost
python weight_forecast_model.py train                # bootstrap on simulated users, save models/weight_forecast.json
python weight_forecast_model.py train --supabase     # train on real users (needs 300 rows; --force overrides)
```

**Data caveat**: there are no real weigh-in histories yet, so the bootstrap model trains on
simulated users (energy-balance style weight change with plateaus, adherence drop-off and scale
noise). Its accuracy on that data shows the pipeline works and beats the baseline there; it is
not evidence of accuracy on real people. Retrain with `--supabase` as users log weight, and compare
the two models' held-out error before trusting the new one. The trained model file is git-ignored.

