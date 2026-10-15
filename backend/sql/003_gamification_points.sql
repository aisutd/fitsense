-- Points (XP) ledger and atomic award function.
-- Run in the Supabase SQL editor after 002_data_model.sql. Safe to re-run.
--
-- user_gamification.total_xp is the running total; xp_events is the history of
-- every award. Point values and level thresholds live in backend/app/gamification.py
-- and are passed in by the backend, so they are defined in one place.

create table if not exists public.xp_events (
  event_id   uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles (user_id) on delete cascade,
  action     text not null,
  points     integer not null check (points > 0),
  source_id  text,          -- optional id of what earned it (e.g. a workout_log_id)
  created_at timestamptz not null default now(),
  -- The same source can't be rewarded twice for the same action.
  -- Rows without a source_id never conflict (NULLs are distinct).
  unique (user_id, action, source_id)
);

create index if not exists xp_events_user_time_idx on public.xp_events (user_id, created_at desc);

alter table public.xp_events enable row level security;

-- Adds points in a single transaction: records the event, bumps total_xp and
-- recalculates level, so concurrent awards can't lose points.
-- p_level_thresholds: minimum XP for each level, ascending, starting at 0
-- (e.g. {0,200,500}: 0-199 = level 1, 200-499 = level 2, 500+ = level 3).
create or replace function public.award_points(
  p_user_id          uuid,
  p_action           text,
  p_points           integer,
  p_level_thresholds integer[],
  p_source_id        text default null
)
returns table (new_total_xp integer, new_level smallint, previous_level smallint, awarded boolean)
language plpgsql
set search_path = public
as $$
declare
  v_previous smallint;
  v_inserted integer;
begin
  if p_points is null or p_points <= 0 then
    raise exception 'p_points must be positive';
  end if;

  -- Fails with a foreign key error (23503) if the profile doesn't exist.
  insert into xp_events (user_id, action, points, source_id)
  values (p_user_id, p_action, p_points, p_source_id)
  on conflict (user_id, action, source_id) do nothing;
  get diagnostics v_inserted = row_count;

  insert into user_gamification (user_id) values (p_user_id)
  on conflict (user_id) do nothing;

  -- Lock the row so concurrent awards for the same user apply one after another.
  select g.level into v_previous
  from user_gamification g
  where g.user_id = p_user_id
  for update;

  -- Duplicate source: nothing awarded, return current state.
  if v_inserted = 0 then
    return query
      select g.total_xp, g.level, v_previous, false
      from user_gamification g where g.user_id = p_user_id;
    return;
  end if;

  return query
    update user_gamification g
    set total_xp = g.total_xp + p_points,
        level    = greatest(1, (select count(*) from unnest(p_level_thresholds) t where t <= g.total_xp + p_points))
    where g.user_id = p_user_id
    returning g.total_xp, g.level, v_previous, true;
end;
$$;

-- Backend only: keep the function away from the public (anon/authenticated) roles.
revoke execute on function public.award_points(uuid, text, integer, integer[], text) from public, anon, authenticated;
