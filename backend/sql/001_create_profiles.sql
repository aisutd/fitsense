-- FitSense onboarding/profile table.
-- Run in the Supabase SQL editor. Safe to re-run.

create table if not exists public.profiles (
  user_id             uuid primary key,
  age                 smallint     not null check (age between 13 and 100),
  height_cm           numeric(5,1) not null check (height_cm between 100 and 250),
  weight_kg           numeric(5,1) not null check (weight_kg between 30 and 300),
  fitness_goal        text not null check (fitness_goal in (
                        'lose_weight', 'build_muscle', 'improve_endurance',
                        'general_fitness', 'increase_flexibility')),
  fitness_level       text not null check (fitness_level in ('beginner', 'intermediate', 'advanced')),
  workout_frequency   smallint not null check (workout_frequency between 1 and 7), -- days per week
  workout_location    text not null check (workout_location in ('home', 'gym', 'outdoors', 'mixed')),
  workout_preferences text[] not null default '{}' check (workout_preferences <@ array[
                        'strength', 'cardio', 'hiit', 'yoga', 'pilates', 'sports', 'calisthenics']::text[]),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- Keep updated_at current on every update.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- No public policies: only the backend (service_role key) can read/write.
alter table public.profiles enable row level security;
