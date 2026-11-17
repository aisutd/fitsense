-- The System's achievements (the list itself lives in backend/app/achievements.py and is copied into
-- public.achievements by the backend). Run once in the Supabase SQL editor; safe to run again.

-- League and shop achievements, and each achievement's rarity
alter table public.achievements drop constraint if exists achievements_category_check;
alter table public.achievements add constraint achievements_category_check check (
  category is null or category in ('workout', 'nutrition', 'sleep', 'activity', 'consistency', 'onboarding', 'league', 'shop'));
alter table public.achievements add column if not exists rarity text
  check (rarity in ('common', 'uncommon', 'rare', 'epic', 'legendary'));

-- What earned it (e.g. which dinner), so the League tab can show the same text as the announcement
alter table public.user_achievements add column if not exists facts jsonb;

-- Awards an achievement once: marks it completed and adds its XP and FitCoins in one transaction.
-- Counter rows (current_value, e.g. avatar changes today) can exist before it's completed.
create or replace function public.award_achievement(
  p_user_id          uuid,
  p_achievement_id   uuid,
  p_xp               integer,
  p_fitcoins         integer,
  p_level_thresholds integer[],
  p_facts            jsonb default null
)
returns table (awarded boolean, new_total_xp integer, new_level smallint, previous_level smallint, fitcoins_balance integer)
language plpgsql
set search_path = public
as $$
declare
  v_claimed  integer;
  v_previous smallint;
begin
  if p_xp < 0 or p_fitcoins < 0 then
    raise exception 'rewards must be non-negative';
  end if;
  insert into user_gamification (user_id) values (p_user_id) on conflict (user_id) do nothing;

  insert into user_achievements (user_id, achievement_id, current_value, completed_at, last_progress_at, facts)
  values (p_user_id, p_achievement_id, 1, now(), now(), p_facts)
  on conflict (user_id, achievement_id) do update
    set completed_at = now(), last_progress_at = now(), facts = excluded.facts
    where user_achievements.completed_at is null;
  get diagnostics v_claimed = row_count;

  select g.level into v_previous from user_gamification g where g.user_id = p_user_id for update;
  if v_claimed = 0 then
    return query select false, g.total_xp, g.level, v_previous, g.fitcoins
      from user_gamification g where g.user_id = p_user_id;
    return;
  end if;

  if p_xp > 0 then
    insert into xp_events (user_id, action, points, source_id)
    values (p_user_id, 'achievement', p_xp, p_achievement_id::text)
    on conflict (user_id, action, source_id) do nothing;
  end if;
  return query
    update user_gamification g
    set total_xp = g.total_xp + p_xp,
        fitcoins = g.fitcoins + p_fitcoins,
        level = greatest(1, (select count(*) from unnest(p_level_thresholds) t where t <= g.total_xp + p_xp))
    where g.user_id = p_user_id
    returning true, g.total_xp, g.level, v_previous, g.fitcoins;
end;
$$;

revoke execute on function public.award_achievement(uuid, uuid, integer, integer, integer[], jsonb) from public, anon, authenticated;
grant execute on function public.award_achievement(uuid, uuid, integer, integer, integer[], jsonb) to service_role;
