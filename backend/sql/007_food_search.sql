-- Local copy of USDA FoodData Central for fast food search (no API calls while the app runs).
-- Run in the Supabase SQL editor after 006_food_logging.sql. Safe to re-run.
-- Then load the data: docker compose run --rm backend python -m app.food.fdc_import

create extension if not exists pg_trgm with schema extensions;
set search_path = public, extensions;

-- 'import' rows come from the USDA download and never expire; 'api' rows are cached API answers.
alter table public.fdc_foods add column if not exists source text not null default 'api'
  check (source in ('api', 'import'));

-- Word search ('simple' keeps words as typed, so "yog" can prefix-match "yogurt")
alter table public.fdc_foods add column if not exists search_text tsvector
  generated always as (to_tsvector('simple', description)) stored;
create index if not exists fdc_foods_search_idx on public.fdc_foods using gin (search_text);

-- Typo-tolerant search ("brocoli")
create index if not exists fdc_foods_trgm_idx on public.fdc_foods using gin (lower(description) gin_trgm_ops);

-- Candidates for a search box query. Every word must match the start of a word in the description
-- (the last one may be half typed), or the whole query must be close to part of it (typos).
-- The backend re-ranks these; it calls this with the secret key, so it's not exposed to the browser.
create or replace function public.search_fdc_foods(words text[], max_results integer default 150)
returns table (fdc_id integer, description text, data_type text, calories_per_100g numeric, match real)
language sql stable
set search_path = public, extensions
as $$
  with clean as (
    select lower(regexp_replace(w, '[^a-zA-Z0-9]', '', 'g')) as w
    from unnest(words) as w
  ), q as (
    select to_tsquery('simple', string_agg(w || ':*', ' & ')) as tsq,
           string_agg(w, ' ') as text
    from clean where w <> ''
  )
  select f.fdc_id, f.description, f.data_type, f.calories_per_100g,
         greatest(ts_rank(f.search_text, q.tsq), word_similarity(q.text, lower(f.description)))::real as match
  from public.fdc_foods f, q
  where q.text is not null
    and f.calories_per_100g is not null
    and f.data_type in ('Survey (FNDDS)', 'SR Legacy', 'Foundation')
    and (f.search_text @@ q.tsq or q.text <% lower(f.description))
  order by (lower(f.description) like split_part(q.text, ' ', 1) || '%') desc,  -- "Banana, raw" before "Bread, banana"
           match desc, length(f.description)
  limit greatest(1, least(max_results, 500));
$$;

revoke execute on function public.search_fdc_foods(text[], integer) from public, anon, authenticated;
