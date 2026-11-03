# Importing steps, sleep and workouts from smartwatches

Research notes for FitSense, November 2026. Things marked *(unverified)* came from secondary sources and
should be checked before relying on them.

## The short version

- **There is no web API for Apple Health or Android's Health Connect.** Both only hand data to a native app on
  the phone. Every aggregator service (Terra, Junction, …) also needs its own SDK inside *your* iOS/Android app
  for those two.
- **Fitbit and Google Fit are effectively closed to new projects.** The Fitbit Web API shuts down on
  **2 Nov 2026**. Its successor, the Google Health API, uses "restricted" scopes that need a Google security
  review, and Google hasn't said it's onboarding new projects. Google Fit's REST API is supported only until
  the end of 2026, with no replacement for web apps.
- **Garmin** only accepts business applications, and has **paused new requests** since early 2026.
- **Cloud APIs a web backend can use today with plain OAuth:** Oura, Polar, WHOOP (no steps), Withings, and
  Strava (workouts only, and its terms ban using the data in AI/ML features like our forecasts).

## Options compared

| Source | Steps | Sleep (stages / score) | Workouts | Works from our web app + FastAPI? | Approval | Cost |
|---|---|---|---|---|---|---|
| Apple Health (HealthKit) | ✓ | ✓ stages | ✓ | **No**: native iOS app only. Web route: user uploads `export.zip` | App Store review (if shipping an app) | Free ($99/yr Apple dev to ship) |
| Health Connect (Android) | ✓ | ✓ stages | ✓ | **No**: on-device, Android app only | Play health-permissions declaration *(unverified details)* | Free |
| Google Fit REST | ✓ | ✓ | ✓ | Closed to new sign-ups, shuts down end of 2026 | n/a | Don't use |
| Fitbit → Google Health API | ✓ | ✓ stages + score | ✓ | Yes (OAuth) | **Restricted scopes + security review**; onboarding unclear | API free; review is usually a paid audit *(unverified)* |
| Garmin Connect Developer Program | ✓ | ✓ stages + score | ✓ | Yes (OAuth, push) | **Business only; new requests paused** | Free to approved partners |
| Oura API v2 | ✓ | ✓ stages + 0–100 score | ✓ | Yes (OAuth 2.0) | ~10 users before approval *(unverified)* | Free; Gen3/Ring 4 owners need an Oura Membership |
| WHOOP API v2 | ✗ | ✓ stages + performance % | ✓ | Yes (OAuth 2.0, webhooks) | 10 members in dev, more needs approval | Free for now |
| Withings | ✓ | ✓ summary + score | ✓ | Yes (OAuth 2.0) | Self-serve dashboard | Believed free *(unverified)* |
| Polar AccessLink | ✓ | ✓ + Nightly Recharge | ✓ | Yes (OAuth 2.0) | Any Polar Flow user can register | Free |
| Strava | ✗ | ✗ | ✓ | Yes (OAuth 2.0) | 1 athlete by default, 10 without review | Free; **no AI/ML use of the data** |
| Aggregators (Terra, Junction/Vital, Thryve, ROOK, Spike, Sahha) | many sources behind one API | | | Cloud sources yes; Apple/Health Connect need their mobile SDK | Sales / trials | Roughly $300–500/month minimums |
| Open Wearables (open source, self-hosted) | Garmin, Polar, Suunto, Strava, … | | | Runs in Docker next to our backend; Apple needs its mobile SDK | None | Free (we host it) |

## Recommended plan

1. **Now (no approvals):** keep manual logging. It already records sleep quality 1–5, and the new date picker
   makes back-filling easy.
2. **Apple Health file import (1–2 weeks), which covers every iPhone/Apple Watch user.**
   - The user uploads the `export.zip` from the Health app.
   - The browser parses it in a Web Worker and sends only daily totals to FastAPI: steps, active minutes,
     sleep per night, workouts.
   - The file is often around 1 GB, so it must be stream-parsed, and parsing it client-side keeps raw health
     data off our server.
3. **Direct OAuth integrations (2–4 weeks), enough for about 10 demo users.**
   - Start with **Oura** and **Polar** (steps + sleep), then **WHOOP** and **Withings**.
   - Add **Strava** for workouts only, and keep its data out of the forecast.
   - Put them behind one "provider adapter" in FastAPI, with a nightly sync job plus webhooks where offered.
   - Store refresh tokens encrypted (Supabase Vault), never in the browser.
   - Delete tokens and synced data when a user disconnects.
4. **Only if the project continues:** a small companion app (Expo/React Native or Capacitor) using the
   HealthKit and Health Connect plugins.
   - That reaches Apple Watch, Pixel, Samsung, and Garmin/Fitbit users whose apps sync to the phone.
   - Alternatives: self-host Open Wearables, or pay for an aggregator once there's budget.
   - Revisit the Google Health API when Google confirms onboarding is open.

## How imported data would map onto our tables

Add `source`, `external_id`, `raw_score` and `synced_at` columns, and make (user_id, date, source) unique so a
re-sync updates rows instead of duplicating them. A `connected_accounts` table holds encrypted tokens.

- **activity_logs**: one row per user per local day.
  - `steps` = the day's total. Pick one source per day; don't add a watch and a phone together.
  - `active_minutes`: vendors define this differently, so choose one per vendor and document it:
    - Fitbit/Google: Active Zone Minutes
    - Garmin: moderate + vigorous intensity minutes
    - Oura: medium + high activity time
    - Apple: Exercise minutes
  - `calories_burned` = **active** calories, not total.
- **workout_logs**: one row per session.
  - `workout_date` = local start date; `duration_minutes` = active time.
  - `completion_status = completed`. Imported workouts then count toward the week's plan (see
    `app/plans.py`, which links workouts to the next open plan day).
  - Deduplicate the same session arriving from several apps: start time ±5 min and similar duration.
- **sleep_logs**: `sleep_date` is the *night of*.
  - Vendors usually label a night by the wake-up date (Oura `day`, Fitbit `dateOfSleep`), so use wake
    date − 1.
  - Skip naps.
  - `hours_slept` = time actually asleep (light/core + deep + REM), not time in bed.

### Turning vendor sleep data into our 1–5 `sleep_quality`

1. **The vendor gives a 0–100 score** (Oura, Fitbit/Google, Garmin, Polar, Withings, WHOOP sleep
   performance): **≥85 → 5, 75–84 → 4, 60–74 → 3, 45–59 → 2, <45 → 1.** These bands roughly match Oura's
   (85+ optimal) and Garmin's (90+ excellent, 60–79 fair) own bands.
2. **Only stages are given** (Apple, Health Connect): compute a 0–100 score from three parts, then use the
   bands above.
   - **50% duration:** 100 for 7–9 h, falling to 0 at 4 h and at 12 h.
   - **25% efficiency** (asleep ÷ in bed): 100 at ≥90%, falling to 0 at 70%.
   - **25% restorative share** (deep + REM): 100 at ≥40%, falling to 0 at 15%.
3. **Only duration is given:**
   - 7–9 h → 4
   - 6–7 h or 9–10 h → 3
   - over 10 h → 3
   - 5–6 h → 2
   - under 5 h → 1

   Never 5, since there's no quality signal.
4. **A user's own 1–5 rating always wins.** Keep the raw vendor score so the bands can be re-tuned later.

## Sources

- Google Health API (Fitbit successor, restricted scopes): https://developers.google.com/health/about
- Google Fit migration and FAQ: https://developer.android.com/health-and-fitness/health-connect/migration/fit/faq
- Health Connect reading limits: https://developer.android.com/health-and-fitness/guides/health-connect/develop/read-data
- Apple sleep values: https://developer.apple.com/documentation/healthkit/hkcategoryvaluesleepanalysis
- Garmin Health API: https://developer.garmin.com/gc-developer-program/health-api/ · pause: https://the5krunner.com/2026/09/14/garmin-developer-api-access-paused/
- Oura API: https://support.ouraring.com/hc/en-us/articles/4415266939155-The-Oura-API
- WHOOP API: https://developer.whoop.com/api
- Polar AccessLink: https://www.polar.com/accesslink-api/
- Strava rate limits and API FAQ: https://developers.strava.com/docs/rate-limits/ · https://communityhub.strava.com/developers-knowledge-base-14/strava-api-faq-12906
- Aggregators: https://tryterra.co/pricing · https://docs.junction.com/wearables/sdks/health/overview.md · https://www.thryve.health/pricing · https://sahha.ai/compare/terra-alternatives/ (a competitor's comparison page, so biased)
- Open Wearables: https://github.com/the-momentum/open-wearables/wiki
