-- Same-day swaps and skip reasons on workout logs, so the weekly plan can tell
-- "I couldn't train today" (gym closed, no equipment) from "this was too much".
--
-- skip_reason: why a plan day was skipped. 'no_equipment' and 'location' don't count as a
--              missed workout when next week's plan is adapted (adaptive_week_two.py).
-- swapped:     the day was done with same-day swaps (POST /plans/{user_id}/swap).
--
-- Safe to run again.

alter table public.workout_logs add column if not exists skip_reason text;
alter table public.workout_logs add column if not exists swapped boolean not null default false;

alter table public.workout_logs drop constraint if exists workout_logs_skip_reason_check;
alter table public.workout_logs add constraint workout_logs_skip_reason_check
  check (skip_reason is null or skip_reason in ('no_equipment', 'location', 'no_time', 'injury', 'other'));
