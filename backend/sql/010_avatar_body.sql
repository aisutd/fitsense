-- Which body the pixel avatar on the league banner uses. Run once in the Supabase SQL editor.
alter table public.user_gamification
  add column if not exists avatar_body text not null default 'male'
  check (avatar_body in ('male', 'female'));
