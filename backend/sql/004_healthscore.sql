-- HealthScore: align the data model with the HealthScore spec.
-- Run in the Supabase SQL editor after 003_gamification_points.sql. Safe to re-run.
--
-- The spec's four categories are workouts, nutrition, sleep and activity. The data
-- model drafted "progress" as the fourth one, so those columns are renamed (the
-- tables are still empty).

do $$
begin
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'health_score_config' and column_name = 'progress_weight') then
    alter table public.health_score_config rename column progress_weight to workout_weight;
  end if;
  if exists (select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'health_scores' and column_name = 'progress_score') then
    alter table public.health_scores rename column progress_score to workout_score;
  end if;
end $$;

-- Snapshot metadata: which window a stored score covers and whether it was
-- calculated from only some categories.
alter table public.health_scores add column if not exists provisional boolean not null default false;
alter table public.health_scores add column if not exists range_start date;
alter table public.health_scores add column if not exists range_end date;

-- Initial weights from the spec (workouts 30%, nutrition 25%, sleep 25%, activity 20%).
-- Adjust later by inserting a row with a higher version.
insert into public.health_score_config (version, workout_weight, nutrition_weight, sleep_weight, activity_weight)
values (1, 0.300, 0.250, 0.250, 0.200)
on conflict (version) do nothing;

-- Macro targets for the nutrition score (null = derived from the calorie target).
alter table public.nutrition_goals add column if not exists carbs_target_g numeric(6,1) check (carbs_target_g >= 0);
alter table public.nutrition_goals add column if not exists fat_target_g numeric(6,1) check (fat_target_g >= 0);

-- progress_goals holds the activity targets (goal_type daily_steps / daily_active_minutes);
-- created_at lets the newest active goal win.
alter table public.progress_goals add column if not exists created_at timestamptz not null default now();
