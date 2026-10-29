-- Weekly workout plans: which week a plan is for, and which plan day a log covers.
-- Run in the Supabase SQL editor. Safe to re-run.

-- Monday of the week the plan is for. One plan per user per week.
alter table public.workout_plans add column if not exists week_start date;
create unique index if not exists workout_plans_user_week
  on public.workout_plans (user_id, week_start);

-- Which day of the plan (plan_exercises.day_number) this workout was. Null for logs not tied
-- to a plan day.
alter table public.workout_logs add column if not exists day_number smallint
  check (day_number between 1 and 7);
