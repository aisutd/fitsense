-- Four-week leagues, FitCoins, badge bonuses, and avatar ownership.
-- Run after 003_gamification_points.sql. Safe to re-run.

alter table public.user_gamification
  add column if not exists fitcoins integer not null default 0 check (fitcoins >= 0),
  add column if not exists league_tier smallint not null default 0 check (league_tier between 0 and 8),
  add column if not exists equipped_avatar text not null default 'starter';

create table if not exists public.user_avatars (
  user_id     uuid not null references public.profiles (user_id) on delete cascade,
  avatar_id   text not null,
  acquired_at timestamptz not null default now(),
  primary key (user_id, avatar_id)
);

create table if not exists public.league_seasons (
  season_start date primary key,
  season_end   date not null,
  finalized_at timestamptz
);

create table if not exists public.league_season_scores (
  season_start date not null references public.league_seasons (season_start) on delete cascade,
  user_id      uuid not null references public.profiles (user_id) on delete cascade,
  tier         smallint not null check (tier between 0 and 8),
  hidden_score numeric(7,3) not null check (hidden_score between 0 and 100),
  health_score numeric(5,2),
  active_days  smallint not null default 0 check (active_days >= 0),
  updated_at   timestamptz not null default now(),
  primary key (season_start, user_id)
);

create index if not exists league_scores_tier_idx
  on public.league_season_scores (season_start, tier, hidden_score desc);

alter table public.user_avatars enable row level security;
alter table public.league_seasons enable row level security;
alter table public.league_season_scores enable row level security;

insert into public.badges (name, description, requirement)
values
  ('first_workout', 'Complete your first workout', '{"completed_workouts":1}'),
  ('ten_workouts', 'Complete ten workouts', '{"completed_workouts":10}'),
  ('seven_day_streak', 'Complete workouts seven days in a row', '{"workout_streak_days":7}')
on conflict (name) do nothing;

-- Each point action grants its corresponding FitCoins in the same transaction.
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
  v_coins integer;
begin
  if p_points is null or p_points <= 0 then
    raise exception 'p_points must be positive';
  end if;

  v_coins := case p_action
    when 'onboarding_completed' then 10
    when 'workout_completed' then 10
    when 'workout_partial' then 5
    when 'meal_logged' then 2
    when 'sleep_logged' then 2
    when 'daily_goals_met' then 5
    when 'streak_7_days' then 20
    else 0
  end;

  insert into xp_events (user_id, action, points, source_id)
  values (p_user_id, p_action, p_points, p_source_id)
  on conflict (user_id, action, source_id) do nothing;
  get diagnostics v_inserted = row_count;

  insert into user_gamification (user_id) values (p_user_id)
  on conflict (user_id) do nothing;

  select g.level into v_previous
  from user_gamification g where g.user_id = p_user_id for update;

  if v_inserted = 0 then
    return query
      select g.total_xp, g.level, v_previous, false
      from user_gamification g where g.user_id = p_user_id;
    return;
  end if;

  return query
    update user_gamification g
    set total_xp = g.total_xp + p_points,
        fitcoins = g.fitcoins + v_coins,
        level = greatest(1, (select count(*) from unnest(p_level_thresholds) t where t <= g.total_xp + p_points))
    where g.user_id = p_user_id
    returning g.total_xp, g.level, v_previous, true;
end;
$$;

create or replace function public.award_badge_coins(p_user_id uuid, p_badge_id uuid, p_fitcoins integer)
returns table (awarded boolean, fitcoins_balance integer)
language plpgsql
set search_path = public
as $$
declare
  v_inserted integer;
  v_balance integer;
begin
  if p_fitcoins < 0 then raise exception 'p_fitcoins must be non-negative'; end if;
  insert into user_gamification (user_id) values (p_user_id) on conflict (user_id) do nothing;
  insert into user_badges (user_id, badge_id) values (p_user_id, p_badge_id)
  on conflict (user_id, badge_id) do nothing;
  get diagnostics v_inserted = row_count;
  if v_inserted > 0 then
    update user_gamification g set fitcoins = g.fitcoins + p_fitcoins
    where g.user_id = p_user_id returning g.fitcoins into v_balance;
  else
    select g.fitcoins into v_balance from user_gamification g where g.user_id = p_user_id;
  end if;
  return query select v_inserted > 0, v_balance;
end;
$$;

create or replace function public.purchase_avatar(p_user_id uuid, p_avatar_id text, p_cost integer)
returns table (purchased boolean, fitcoins_balance integer)
language plpgsql
set search_path = public
as $$
declare
  v_balance integer;
begin
  if p_cost < 0 then raise exception 'p_cost must be non-negative'; end if;
  insert into user_gamification (user_id) values (p_user_id) on conflict (user_id) do nothing;
  insert into user_avatars (user_id, avatar_id) values (p_user_id, 'starter') on conflict do nothing;

  if exists (select 1 from user_avatars a where a.user_id = p_user_id and a.avatar_id = p_avatar_id) then
    select g.fitcoins into v_balance from user_gamification g where g.user_id = p_user_id;
    return query select false, v_balance;
    return;
  end if;

  update user_gamification g set fitcoins = g.fitcoins - p_cost
  where g.user_id = p_user_id and g.fitcoins >= p_cost
  returning g.fitcoins into v_balance;
  if not found then raise exception 'not enough FitCoins' using errcode = 'P0001'; end if;

  insert into user_avatars (user_id, avatar_id) values (p_user_id, p_avatar_id);
  return query select true, v_balance;
end;
$$;

create or replace function public.finalize_league_season(p_season_start date)
returns boolean
language plpgsql
set search_path = public
as $$
declare
  v_finalized timestamptz;
begin
  insert into league_seasons (season_start, season_end)
  values (p_season_start, p_season_start + 27)
  on conflict (season_start) do nothing;

  select finalized_at into v_finalized from league_seasons
  where season_start = p_season_start for update;
  if v_finalized is not null or current_date <= p_season_start + 27 then return false; end if;

  insert into user_gamification (user_id)
  select distinct s.user_id from league_season_scores s where s.season_start = p_season_start
  on conflict (user_id) do nothing;

  with ranked as (
    select s.user_id, s.tier,
      row_number() over (partition by s.tier order by s.hidden_score desc, s.user_id) as place,
      count(*) over (partition by s.tier) as members
    from league_season_scores s where s.season_start = p_season_start
  ), movement as (
    select user_id, tier,
      case
        when members >= 5 and place <= ceil(members * 0.2) and tier < 8 then 1
        when members >= 5 and place > members - ceil(members * 0.2) and tier > 0 then -1
        else 0
      end as delta
    from ranked
  )
  update user_gamification g
  set league_tier = greatest(0, least(8, g.league_tier + m.delta))
  from movement m where m.user_id = g.user_id and m.delta <> 0;

  update league_seasons set finalized_at = now() where season_start = p_season_start;
  return true;
end;
$$;

revoke execute on function public.award_badge_coins(uuid, uuid, integer) from public, anon, authenticated;
revoke execute on function public.purchase_avatar(uuid, text, integer) from public, anon, authenticated;
revoke execute on function public.finalize_league_season(date) from public, anon, authenticated;
grant execute on function public.award_points(uuid, text, integer, integer[], text) to service_role;
grant execute on function public.award_badge_coins(uuid, uuid, integer) to service_role;
grant execute on function public.purchase_avatar(uuid, text, integer) to service_role;
grant execute on function public.finalize_league_season(date) to service_role;
