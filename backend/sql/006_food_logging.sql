-- Food logging: FoodData Central caches and the extra meal_items fields the review screen needs.
-- Run in the Supabase SQL editor after 005_accounts.sql. Safe to re-run.

-- Search results from FoodData Central, keyed by the normalised search text.
-- Keeps us well under FDC's hourly rate limit; entries older than 30 days are refreshed.
create table if not exists public.fdc_search_cache (
  query      text primary key,
  results    jsonb not null,          -- [{fdc_id, description, data_type, calories_per_100g, rank_score}]
  fetched_at timestamptz not null default now()
);

-- Each meal ingredient as shown on the review screen.
alter table public.meal_items add column if not exists unit text;                      -- canonical unit, null = count
alter table public.meal_items add column if not exists portion_label text;             -- e.g. "3 × 1 large (50 g)"
alter table public.meal_items add column if not exists needs_review boolean not null default false;
alter table public.meal_items add column if not exists source_dish text;               -- recipe it came from
alter table public.meal_items add column if not exists alternatives jsonb not null default '[]';
alter table public.meal_items add column if not exists created_at timestamptz not null default now();

-- Portions are replaced as a set whenever a food is (re)fetched.
create index if not exists fdc_food_portions_fdc_idx on public.fdc_food_portions (fdc_id);

create index if not exists meal_entries_user_status_date_idx on public.meal_entries (user_id, status, log_date);

alter table public.fdc_search_cache enable row level security;
