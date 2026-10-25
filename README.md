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

## Backend: Profiles (onboarding data)

### Setup

1. Copy `.env.example` to `.env` in the repo root and fill in `SUPABASE_URL` and `SUPABASE_KEY`.
   Use the **service_role** key: the `profiles` table has row level security enabled, so the anon key can't read or write it.
2. In the Supabase dashboard, open the **SQL Editor**, paste in `backend/sql/001_create_profiles.sql`, and run it. It's safe to run again.
3. Run `docker compose up -d --build`. The API is at http://localhost:8000, and interactive docs are at http://localhost:8000/docs.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `PUT` | `/profiles/{user_id}` | Create or replace a user's profile. Returns the stored profile. |
| `GET` | `/profiles/{user_id}` | Get a user's profile, or `404` if none exists. |

`user_id` is a UUID, which the frontend generates for now (`crypto.randomUUID()`). Height and weight are **metric** (cm and kg). Invalid data is rejected with `422`.

Example request body:

```json
{
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
| `age` | 13–100 |
| `height_cm` | 100–250 |
| `weight_kg` | 30–300 |
| `fitness_goal` | `lose_weight`, `build_muscle`, `improve_endurance`, `general_fitness`, `increase_flexibility` |
| `fitness_level` | `beginner`, `intermediate`, `advanced` |
| `workout_frequency` | 1–7 (days per week) |
| `workout_location` | `home`, `gym`, `outdoors`, `mixed` |
| `workout_preferences` | optional list of `strength`, `cardio`, `hiit`, `yoga`, `pilates`, `sports`, `calisthenics` |

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Supabase needed
python scripts/smoke_test_profiles.py         # live test against the running backend + Supabase
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
python progress_forecast.py --user f449eafd-7993-4a4b-ad52-8adb9fef3270  # Grace's forecast graph
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
python progress_forecast.py --user <user_id>   # graph one user's forecast and open it in VS Code
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

`--user` saves `charts/forecast-<user_id>.png` (matplotlib) and opens it as a tab in VS Code
with the `code` command; pass `--no-open` to only save it. There is one panel per metric: logged
weeks as a solid line, the forecast as a dashed line in the shaded area, and under HealthScore
each category's score now and in 12 weeks with its weight. It is styled like the website's HealthScore screen: the
night palette, neon category frames, pixel-art icons copied from `src/icons.js`, and the VT323
pixel font, bundled in `assets/fonts/` with its license (SIL Open Font License). `charts/` is git-ignored because the
graphs contain users' data. If `code` isn't found, run **Shell Command: Install 'code' command in
PATH** from VS Code's Command Palette.
