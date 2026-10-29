-- Username/password accounts for testing (to be replaced by Supabase Auth later).
-- Run in the Supabase SQL editor after 004_healthscore.sql. Safe to re-run.
--
-- An account's user_id becomes the user's profiles.user_id once onboarding is
-- finished. Passwords are never stored: only a salted scrypt hash made by the
-- backend (backend/app/passwords.py).

create table if not exists public.accounts (
  user_id       uuid primary key default gen_random_uuid(),
  username      text not null check (username ~ '^[A-Za-z0-9_.-]{3,30}$'),
  password_hash text not null,
  created_at    timestamptz not null default now(),
  last_login_at timestamptz
);

-- Usernames are unique regardless of case ("Ava" and "ava" are the same user).
create unique index if not exists accounts_username_lower_idx on public.accounts (lower(username));

-- Backend only (secret key).
alter table public.accounts enable row level security;
