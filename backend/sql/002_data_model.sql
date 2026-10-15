-- FitSense data model (from the "FitSense Data Model" page).
-- Run in the Supabase SQL editor after 001_create_profiles.sql. Safe to re-run.
--
-- Additive only: profiles keeps its workout columns so the live /profiles API keeps
-- working. They are copied into user_preferences and can be dropped once nothing
-- reads them from profiles.
--
-- Every table has RLS enabled with no public policies: only the backend
-- (secret/service_role key) can read or write.

-- ---------------------------------------------------------------------------
-- User profiles & onboarding
-- ---------------------------------------------------------------------------

alter table public.profiles add column if not exists name text;

create table if not exists public.user_preferences (
  preference_id           uuid primary key default gen_random_uuid(),
  user_id                 uuid not null unique references public.profiles (user_id) on delete cascade,
  workout_days_per_week   smallint check (workout_days_per_week between 1 and 7),
  workout_location        text check (workout_location in ('home', 'gym', 'outdoors', 'mixed')),
  available_equipment     text[] not null default '{}',
  preferred_workout_types text[] not null default '{}' check (preferred_workout_types <@ array[
                            'strength', 'cardio', 'hiit', 'yoga', 'pilates', 'sports', 'calisthenics']::text[])
);

-- Copy existing onboarding answers over (no-op for users who already have a row).
insert into public.user_preferences (user_id, workout_days_per_week, workout_location, preferred_workout_types)
select user_id, workout_frequency, workout_location, workout_preferences
from public.profiles
on conflict (user_id) do nothing;

-- ---------------------------------------------------------------------------
-- Workout & personalization
-- ---------------------------------------------------------------------------

create table if not exists public.exercises (
  exercise_id  uuid primary key default gen_random_uuid(),
  name         text not null unique,
  muscle_group text,
  difficulty   text check (difficulty in ('beginner', 'intermediate', 'advanced')),
  equipment    text,
  workout_type text check (workout_type in ('strength', 'cardio', 'hiit', 'yoga', 'pilates', 'sports', 'calisthenics')),
  instructions text
);

create table if not exists public.workout_plans (
  plan_id       uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (user_id) on delete cascade,
  plan_name     text not null,
  fitness_goal  text,
  days_per_week smallint check (days_per_week between 1 and 7),
  created_at    timestamptz not null default now()
);

create table if not exists public.plan_exercises (
  plan_exercise_id uuid primary key default gen_random_uuid(),
  plan_id          uuid not null references public.workout_plans (plan_id) on delete cascade,
  exercise_id      uuid not null references public.exercises (exercise_id),
  day_number       smallint not null check (day_number between 1 and 7),
  sets             smallint check (sets > 0),
  reps             smallint check (reps > 0),
  duration_minutes smallint check (duration_minutes > 0)
);

create table if not exists public.workout_logs (
  workout_log_id    uuid primary key default gen_random_uuid(),
  user_id           uuid not null references public.profiles (user_id) on delete cascade,
  plan_id           uuid references public.workout_plans (plan_id) on delete set null,
  workout_date      date not null default current_date,
  duration_minutes  smallint check (duration_minutes >= 0),
  completion_status text not null check (completion_status in ('completed', 'partial', 'skipped'))
);

-- ---------------------------------------------------------------------------
-- Nutrition tracking
-- ---------------------------------------------------------------------------

create table if not exists public.nutrition_logs (
  nutrition_id uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles (user_id) on delete cascade,
  log_date     date not null,
  calories     integer check (calories >= 0),
  protein_g    numeric(6,1) check (protein_g >= 0),
  carbs_g      numeric(6,1) check (carbs_g >= 0),
  fats_g       numeric(6,1) check (fats_g >= 0),
  water_ml     integer check (water_ml >= 0),
  unique (user_id, log_date)
);

create table if not exists public.nutrition_goals (
  nutrition_goal_id    uuid primary key default gen_random_uuid(),
  user_id              uuid not null references public.profiles (user_id) on delete cascade,
  daily_calorie_target integer check (daily_calorie_target > 0),
  protein_target_g     numeric(6,1) check (protein_target_g >= 0),
  water_target_ml      integer check (water_target_ml >= 0),
  created_at           timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Sleep tracking
-- ---------------------------------------------------------------------------

create table if not exists public.sleep_logs (
  sleep_id      uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (user_id) on delete cascade,
  sleep_date    date not null,
  hours_slept   numeric(4,2) check (hours_slept between 0 and 24),
  sleep_quality smallint check (sleep_quality between 1 and 5),
  unique (user_id, sleep_date)
);

create table if not exists public.sleep_goals (
  sleep_goal_id uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles (user_id) on delete cascade,
  target_hours  numeric(4,2) not null check (target_hours between 0 and 24),
  created_at    timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Activity & progress
-- ---------------------------------------------------------------------------

create table if not exists public.activity_logs (
  activity_id     uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (user_id) on delete cascade,
  log_date        date not null,
  steps           integer check (steps >= 0),
  active_minutes  smallint check (active_minutes >= 0),
  calories_burned integer check (calories_burned >= 0),
  unique (user_id, log_date)
);

create table if not exists public.body_measurements (
  measurement_id uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (user_id) on delete cascade,
  recorded_at    timestamptz not null default now(),
  weight_kg      numeric(5,1) check (weight_kg between 30 and 300)
);

create table if not exists public.progress_goals (
  progress_goal_id uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.profiles (user_id) on delete cascade,
  goal_type        text not null,
  target_value     numeric not null,
  target_date      date,
  status           text not null default 'active' check (status in ('active', 'achieved', 'abandoned'))
);

-- ---------------------------------------------------------------------------
-- HealthScore
-- ---------------------------------------------------------------------------

create table if not exists public.health_score_config (
  config_id        uuid primary key default gen_random_uuid(),
  activity_weight  numeric(4,3) not null,
  nutrition_weight numeric(4,3) not null,
  sleep_weight     numeric(4,3) not null,
  progress_weight  numeric(4,3) not null,
  version          integer not null unique,
  check (activity_weight + nutrition_weight + sleep_weight + progress_weight = 1.000)
);

create table if not exists public.health_scores (
  score_id        uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (user_id) on delete cascade,
  score           numeric(5,2) check (score between 0 and 100),
  activity_score  numeric(5,2) check (activity_score between 0 and 100),
  nutrition_score numeric(5,2) check (nutrition_score between 0 and 100),
  sleep_score     numeric(5,2) check (sleep_score between 0 and 100),
  progress_score  numeric(5,2) check (progress_score between 0 and 100),
  calculated_at   timestamptz not null default now(),
  config_id       uuid references public.health_score_config (config_id)
);

-- ---------------------------------------------------------------------------
-- Forecasting & predictions
-- ---------------------------------------------------------------------------

create table if not exists public.progress_forecasts (
  forecast_id     uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (user_id) on delete cascade,
  prediction_type text not null,
  predicted_value numeric not null,
  target_date     date,
  generated_at    timestamptz not null default now(),
  model_version   text
);

-- ---------------------------------------------------------------------------
-- Gamification
-- ---------------------------------------------------------------------------

create table if not exists public.user_gamification (
  user_id  uuid primary key references public.profiles (user_id) on delete cascade,
  total_xp integer not null default 0 check (total_xp >= 0),
  level    smallint not null default 1 check (level >= 1)
);

create table if not exists public.badges (
  badge_id    uuid primary key default gen_random_uuid(),
  name        text not null unique,
  description text,
  requirement jsonb
);

create table if not exists public.user_badges (
  user_id   uuid not null references public.profiles (user_id) on delete cascade,
  badge_id  uuid not null references public.badges (badge_id) on delete cascade,
  earned_at timestamptz not null default now(),
  primary key (user_id, badge_id)
);

create table if not exists public.user_streaks (
  user_id             uuid not null references public.profiles (user_id) on delete cascade,
  streak_type         text not null check (streak_type in ('workout', 'daily_goals', 'sleep')),
  current_streak      smallint not null default 0 check (current_streak >= 0),
  longest_streak      smallint not null default 0 check (longest_streak >= 0),
  last_completed_date date,
  primary key (user_id, streak_type)
);

create table if not exists public.missions (
  mission_id  uuid primary key default gen_random_uuid(),
  title       text not null,
  description text,
  xp_reward   integer not null check (xp_reward > 0),
  frequency   text not null default 'daily' check (frequency in ('daily', 'weekly'))
);

create table if not exists public.user_missions (
  user_mission_id uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.profiles (user_id) on delete cascade,
  mission_id      uuid not null references public.missions (mission_id) on delete cascade,
  assigned_date   date not null default current_date,
  completed_at    timestamptz,
  status          text not null default 'assigned' check (status in ('assigned', 'completed', 'expired')),
  unique (user_id, mission_id, assigned_date)
);

-- ---------------------------------------------------------------------------
-- Food logging (USDA FoodData Central)
-- ---------------------------------------------------------------------------

create table if not exists public.fdc_foods (
  fdc_id             integer primary key,
  description        text not null,
  data_type          text,
  brand_owner        text,
  gtin_upc           text,
  calories_per_100g  numeric(7,2),
  protein_g_per_100g numeric(6,2),
  carbs_g_per_100g   numeric(6,2),
  fat_g_per_100g     numeric(6,2),
  other_nutrients    jsonb,
  publication_date   date,
  fetched_at         timestamptz not null default now()
);

create table if not exists public.fdc_food_portions (
  portion_id     uuid primary key default gen_random_uuid(),
  fdc_id         integer not null references public.fdc_foods (fdc_id) on delete cascade,
  fdc_portion_id integer,
  label          text not null,
  amount         numeric not null default 1,
  gram_weight    numeric(7,2) not null check (gram_weight > 0)
);

create table if not exists public.meal_entries (
  meal_id      uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles (user_id) on delete cascade,
  log_date     date not null default current_date,
  meal_type    text check (meal_type in ('breakfast', 'lunch', 'dinner', 'snack')),
  raw_text     text,
  display_name text,
  image_url    text,
  status       text not null default 'estimated' check (status in ('estimated', 'confirmed', 'discarded')),
  calories     numeric(7,1),
  protein_g    numeric(6,1),
  carbs_g      numeric(6,1),
  fat_g        numeric(6,1),
  created_at   timestamptz not null default now(),
  confirmed_at timestamptz
);

create table if not exists public.meal_items (
  meal_item_id     uuid primary key default gen_random_uuid(),
  meal_id          uuid not null references public.meal_entries (meal_id) on delete cascade,
  fdc_id           integer references public.fdc_foods (fdc_id),
  portion_id       uuid references public.fdc_food_portions (portion_id) on delete set null,
  ingredient_text  text,
  quantity         numeric(7,2) check (quantity >= 0),
  grams            numeric(7,1) check (grams >= 0),
  is_assumed       boolean not null default false,
  match_confidence numeric(3,2) check (match_confidence between 0 and 1),
  calories         numeric(7,1),
  protein_g        numeric(6,1),
  carbs_g          numeric(6,1),
  fat_g            numeric(6,1)
);

-- ---------------------------------------------------------------------------
-- Achievements
-- ---------------------------------------------------------------------------

create table if not exists public.achievements (
  achievement_id uuid primary key default gen_random_uuid(),
  code           text not null unique,
  name           text not null,
  description    text,
  kind           text not null check (kind in ('one_time', 'tiered')),
  category       text check (category in ('workout', 'nutrition', 'sleep', 'activity', 'consistency', 'onboarding')),
  metric         text,
  is_hidden      boolean not null default false,
  created_at     timestamptz not null default now()
);

create table if not exists public.achievement_tiers (
  tier_id        uuid primary key default gen_random_uuid(),
  achievement_id uuid not null references public.achievements (achievement_id) on delete cascade,
  tier_level     smallint not null check (tier_level >= 1),
  tier_name      text,
  threshold      numeric not null check (threshold > 0),
  xp_reward      integer not null default 0 check (xp_reward >= 0),
  badge_id       uuid references public.badges (badge_id) on delete set null,
  unique (achievement_id, tier_level)
);

create table if not exists public.user_achievements (
  user_id          uuid not null references public.profiles (user_id) on delete cascade,
  achievement_id   uuid not null references public.achievements (achievement_id) on delete cascade,
  current_value    numeric not null default 0,
  current_tier     smallint not null default 0 check (current_tier >= 0),
  last_progress_at timestamptz,
  completed_at     timestamptz,
  primary key (user_id, achievement_id)
);

create table if not exists public.achievement_unlocks (
  user_id     uuid not null references public.profiles (user_id) on delete cascade,
  tier_id     uuid not null references public.achievement_tiers (tier_id) on delete cascade,
  unlocked_at timestamptz not null default now(),
  xp_awarded  integer not null default 0 check (xp_awarded >= 0),
  primary key (user_id, tier_id)
);

-- ---------------------------------------------------------------------------
-- Indexes for per-user lookups by date
-- ---------------------------------------------------------------------------

create index if not exists workout_logs_user_date_idx  on public.workout_logs (user_id, workout_date desc);
create index if not exists health_scores_user_time_idx on public.health_scores (user_id, calculated_at desc);
create index if not exists meal_entries_user_date_idx  on public.meal_entries (user_id, log_date);
create index if not exists meal_items_meal_idx         on public.meal_items (meal_id);
create index if not exists plan_exercises_plan_idx     on public.plan_exercises (plan_id);

-- ---------------------------------------------------------------------------
-- Row level security: backend-only access
-- ---------------------------------------------------------------------------

do $$
declare t text;
begin
  foreach t in array array[
    'user_preferences', 'exercises', 'workout_plans', 'plan_exercises', 'workout_logs',
    'nutrition_logs', 'nutrition_goals', 'sleep_logs', 'sleep_goals',
    'activity_logs', 'body_measurements', 'progress_goals',
    'health_score_config', 'health_scores', 'progress_forecasts',
    'user_gamification', 'badges', 'user_badges', 'user_streaks', 'missions', 'user_missions',
    'fdc_foods', 'fdc_food_portions', 'meal_entries', 'meal_items',
    'achievements', 'achievement_tiers', 'user_achievements', 'achievement_unlocks'
  ] loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
end $$;
