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
   - `008_leagues_fitcoins.sql`: FitCoins wallet, avatar inventory, four-week league seasons, and promotion rules
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
| `GET` | `/gamification/{user_id}` | Total points, level, FitCoins, and equipped avatar |
| `GET` | `/gamification/{user_id}/league` | Current four-week league, private-score ranking, and top-five podium |
| `GET` | `/gamification/{user_id}/avatars` | FitCoin balance, avatar shop, owned badges, and streaks |
| `POST` | `/gamification/{user_id}/avatars/{avatar_id}/purchase` | Buy an avatar with FitCoins |
| `PUT` | `/gamification/{user_id}/avatars/{avatar_id}/equip` | Equip an owned avatar |
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
- FitCoins are a separate spendable balance. A completed workout grants 50 XP and 10 FitCoins; partial workouts, sleep, meals, daily goals, and seven-day workout streaks have backend-set rewards. Repeated logs do not pay twice for the same source.
- League seasons last four weeks. Standings use the season-to-date HealthScore and consistency (days with any check-in), while the exact ranking score stays hidden. **Every player with a season HealthScore is ranked**, whether or not they've opened the league page: standings are computed for everyone in one bulk pass and stored in `league_season_scores`, refreshed at most every 10 minutes (after the response, so nobody waits for it). With at least five scored players in a league, the top 20% move up and the bottom 20% move down when the season closes; smaller leagues hold their tiers. The podium shows the top five.
- Completing a first or tenth workout, or every 7th day in a row of the daily check-in streak (see below; recovery days count when anything is logged), unlocks a badge and a FitCoin bonus. FitCoins buy avatars in the shop on the **League** tab (with the league standing, podium, streaks and badges); the starter avatar is free.
- **Reward pop-ups**: logging anything that earns XP or FitCoins plays pixel-art effects from the button you pressed, and they grow with your **daily check-in streak** (consecutive days with any log, returned as `checkin_streak` by every log endpoint; recovery days with only steps or sleep keep it going): 1 day sparkle, 3 days gold plus a coin fountain, 5 days a "x5 DAY STREAK" counter, 7 days confetti, 14 days confetti from both sides. Badges and level-ups get a toast. Reduced motion shows only the text. Effects come from [pixelfx](https://github.com/patch-gg/pixelfx) (MIT), vendored in `src/fx/pixelfx`.
- Unknown users get `404`; unknown actions get `422`.

### HealthScore

An overall 0–100 score from four categories: **workouts 30%, nutrition 25%, sleep 25%, activity 20%** (weights come from the newest `health_score_config` row). The calculation is in `backend/app/healthscore.py` as reusable functions, one per category; `healthscore_repo.py` loads one user's logs (or everyone's, in a few bulk queries) and scores them in memory.

**The screen scores one day** (`range=day`, the default), with a date picker to look back at any earlier day. **Tap a section of the ring, or a category card, to log it**: a small pop-up logs that category for the day on screen (one tap for a workout result, chips or a number for sleep and steps, a described meal looked up in the USDA data, with the full meal logger one click away):

| Category | That day's score |
|---|---|
| Workouts | completed 100, partial 50, skipped 0. A day with nothing logged is a **rest day** (left out, not "missing"), unless skipping it makes the week's plan impossible (more planned workouts still needed than days left after it), which scores 0. Planned days per week come from the newest workout plan, else onboarding. Days before sign-up never count as missed. |
| Nutrition | how closely the day's **confirmed meals** match the targets (calories 40%, protein 30%, carbs 15%, fat 15%). Without a nutrition goal, targets are estimated from the profile. |
| Sleep | the night *before* the day (the one you woke up from), closeness to the sleep target (default 8 h): 7 h → 88 |
| Activity | min(100, steps ÷ step target × 100), default 8,000 steps; active minutes (default 30) when no steps are logged |

`range=week|last-week|month` scores a window instead (used by leagues and forecasts): workouts completed ÷ scheduled, nutrition needs meals on 3+ days, sleep and activity are averaged.

A category without data is left out and the overall score is marked `provisional` (a rest day doesn't count as missing); with no data at all, `overall_score` is `null`. HealthScore is a motivational wellness metric, not a medical assessment.

| Method | Path | Description |
|---|---|---|
| `GET` | `/healthscore/{user_id}?range=day\|week\|last-week\|month&end_date=YYYY-MM-DD` | Score one day (default) or a window ending on `end_date` (send the user's local date) |
| `GET` | `/logs/{user_id}/day/{date}` | Everything logged that day: workouts, steps, confirmed meals, and the night of sleep before it |
| `POST` | `/healthscore/{user_id}/snapshots` | Calculate and save to `health_scores` |
| `GET` | `/healthscore/{user_id}/history` | Saved scores, newest first |
| `POST` | `/logs/{user_id}/workouts` | Log a workout (`completed`, `partial`, `skipped`). Without `plan_id`/`day_number` it's linked to that week's next open workout-plan day. |
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
it's safe to re-run and checks every login. Each run also **fills in the last 7 days** of logs in every player's habits
(`--refresh-days N`; only empty days/categories, so hand-logged data stays): re-run it every few days to keep "today" populated.

### Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                        # unit tests, no Supabase needed
python scripts/smoke_test_profiles.py         # live tests against the running backend + Supabase
python scripts/smoke_test_gamification.py
python scripts/seed_sample_users.py           # sample players + HealthScore checks against the spec's examples
python scripts/seed_test_users.py             # 200 test players (tester001-tester200) + their last 7 days of logs
python scripts/smoke_test_food.py             # food logging end to end (real model, FDC and Supabase)
python ml/food_ner/evaluate.py                # food model accuracy on the hand-written test set
```

## Wearables and smartwatches

Options for importing steps, sleep and workouts from watches and phones (Apple Health, Health Connect,
Oura, Polar, Garmin, Fitbit, aggregators), what each needs, and a phased plan:
[docs/wearable-integration.md](docs/wearable-integration.md).

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

**Recovery days**: every week keeps at least one (at most 6 training days, even if onboarding says 7).
Training days are spread over the week with a recovery day between them where possible
(3 days → Mon/Wed/Fri, 6 days → Sunday off), and the rest of the week is re-planned as days get
logged. Recovery days come with an optional light routine: an easy walk and one beginner stretch
each for the legs, upper body and core. The daily HealthScore treats them as rest days.

**In the app**: the **Plan** tab shows this week's plan (`GET /plans/{user_id}/current?today=YYYY-MM-DD`,
built and saved on first view by `backend/app/plans.py`), why it changed from last week, a week strip
of training and recovery days, the recovery routine, and buttons to log each plan day. Workouts logged anywhere else (the HealthScore page's Workout tab) are linked to the
week's next open plan day, and older unlinked logs are matched the same way, so the adaptation sees them.

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
HealthScore 1, 4 and 12 weeks ahead, each with an **80% range**. The app shows them on the Forecast tab
(`GET /forecasts/{user_id}`: predictions with `low`/`high`, plus the weekly history they were fitted on).
Each metric is averaged per week (Monday–Sunday, UTC; the current, unfinished week is left out) and fit
with a weighted linear regression:

- **Damped trend**: next week follows the fitted trend, later weeks less and less (Holt's damped
  trend, `DAMPING = 0.8`), so a trend from a few noisy weeks can't run away over 12 weeks: the total
  change is at most 5 weeks' worth of the current trend.
- **Only full weeks**: the week a user joined (unless on a Monday) is left out, and a week of steps
  needs at least 3 logged days, so a partial week doesn't fake a trend.
- **Realistic bounds**: workouts never go above the plan or the user's best week so far; ranges come
  from the user's week-to-week variation, blended with a typical spread per metric while data is thin.

- **Adapts weekly**: it is refit every week, and a week 4 weeks old counts half as much as the
  latest one, so a change in habits shows up in the next forecast.
- **Uses the profile**: the trend is pulled toward a prior from the user's preferences. Workouts
  start from `workout_frequency`; weight follows the `fitness_goal` (lose: −0.5 kg/week, the low
  end of the CDC's 0.45–0.9; build muscle: Aragon's lean-gain rate by `fitness_level`; other goals:
  no change). With little data the prior dominates; after about a month the user's own trend does.
- **Weight uses the workout forecast**: the goal's expected weight change is scaled by the share
  of planned workouts the user is forecast to complete, and capped at ±1 kg/week.
- **HealthScore comes from the HealthScore screen's own code**: each past week is scored as a
  7-day window by `backend/app/healthscore_repo.score` (in memory, from one load of the user's logs), then the
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

