"""Weekly linear-regression forecasts of body weight, workouts, daily steps and HealthScore.

Each metric is averaged per week (Monday to Sunday, UTC) and fit with a weighted linear
regression on the user's own history. Two things make it adapt to the user:

- Recent weeks count more (WEEK_HALF_LIFE), and the forecast is refit every week from the
  weeks completed so far, so a change in habits shows up in the next forecast.
- The trend is pulled toward a prior from the user's profile: no change for workouts (their
  planned workout_frequency is the starting point), and the fitness_goal's expected rate for
  weight. With little history the prior dominates; as weeks accumulate the user's trend wins.

The weight forecast uses the workout forecast: the goal's expected weight change is scaled by
how much of their planned workouts the user is forecast to complete next week.

The HealthScore forecast uses the backend's own calculation (backend/app/healthscore.py and
healthscore_repo.py, the code behind the HealthScore screen). Each past week is scored as the
screen's "Last 7 Days" view would have shown it, each category's weekly score is forecast
separately, and the forecasts are combined with the active health_score_config weights, the
same way the screen's overall score is.

    python progress_forecast.py --user <user_id> [--no-open]  # graph one user's forecast in VS Code
    python progress_forecast.py weekly [--dry-run]  # forecast every user, save to progress_forecasts

Run `weekly` once a week (for example from cron on Monday). A user who already has forecasts
from this week and MODEL_VERSION is skipped, so running it twice adds nothing.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import numpy as np

from exercise_ranker import fetch_all

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "backend"))
from app import healthscore as hs  # noqa: E402  (pure functions; healthscore_repo loads lazily)

MODEL_VERSION = "linreg-weekly-v1"
# Weight forecasts corrected by the XGBoost model in weight_forecast_model.py.
ML_MODEL_VERSION = "linreg+xgb-weekly-v1"
HORIZONS = (1, 4, 12)  # weeks ahead of the last completed week
# A week this many weeks old counts half as much as the most recent one.
WEEK_HALF_LIFE = 4.0
# How firmly the profile prior holds the slope, in the units of the data's own evidence
# (sum of weight * (week - mean week)^2). Four equally weighted weeks give 5.
PRIOR_STRENGTH = 5.0

# Expected weight change per week while doing every planned workout:
# - Loss: CDC recommends 1-2 lb (0.45-0.9 kg) a week; the forecast uses the low end.
# - Gain: Aragon's lean-gain rates, as a share of body weight per month, low end by level.
WEIGHT_LOSS_PER_WEEK = 0.5
MUSCLE_GAIN_PER_MONTH = {"beginner": 0.01, "intermediate": 0.005, "advanced": 0.0025}
WEEKS_PER_MONTH = 52 / 12
MAX_WEEKLY_WEIGHT_CHANGE = 1.0  # kg; the top of the CDC's safe range
# Weeks of HealthScore history to rebuild. Each week is one backend calculation (about a second).
MAX_HEALTH_WEEKS = 12

METRICS = {
    # prediction_type: (label, unit, lowest, highest)
    "weight_kg": ("Weight", "kg", 30.0, 300.0),
    "workouts_per_week": ("Workouts", "per week", 0.0, 7.0),
    "daily_steps": ("Steps", "per day", 0.0, None),
    "health_score": ("HealthScore", "", 0.0, 100.0),
}


def to_date(value):
    """A date from a Supabase date or timestamp string."""
    return date.fromisoformat(str(value)[:10])


def week_start(day):
    return day - timedelta(days=day.weekday())


def last_complete_week(today):
    """Monday of the most recent week that has fully ended. The current week is still partial."""
    return week_start(today) - timedelta(days=7)


def week_index(day, origin):
    """0 for the origin week, -1 for the week before, and so on."""
    return (week_start(day) - origin).days // 7


def weekly_means(rows, date_key, value_key, origin):
    """[(week index, mean value)] over completed weeks, skipping rows without a value."""
    weeks = {}
    for row in rows:
        if row.get(value_key) is None or not row.get(date_key):
            continue
        t = week_index(to_date(row[date_key]), origin)
        if t <= 0:
            weeks.setdefault(t, []).append(float(row[value_key]))
    return [(t, sum(values) / len(values)) for t, values in sorted(weeks.items())]


def weekly_workouts(logs, first_day, origin):
    """[(week index, completed workouts)] for every completed week since first_day, zeros included."""
    first = week_index(first_day, origin)
    counts = {t: 0 for t in range(first, 1)}
    for log in logs:
        if log["completion_status"] == "completed" and log.get("workout_date"):
            t = week_index(to_date(log["workout_date"]), origin)
            if t in counts:
                counts[t] += 1
    return sorted(counts.items())


def fit_trend(points, prior_slope):
    """(level at week 0, slope per week) from a recency-weighted least-squares line.

    The prior is one extra equation, slope = prior_slope, weighted by PRIOR_STRENGTH. That keeps
    the fit defined with a single week of data and lets the user's own trend take over as
    weeks accumulate.
    """
    t = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    root_w = np.sqrt(0.5 ** (-t / WEEK_HALF_LIFE))
    A = np.vstack([np.column_stack([root_w, root_w * t]), [0.0, np.sqrt(PRIOR_STRENGTH)]])
    b = np.append(root_w * y, np.sqrt(PRIOR_STRENGTH) * prior_slope)
    (level, slope), *_ = np.linalg.lstsq(A, b, rcond=None)
    return float(level), float(slope)


# prediction_type for each HealthScore category's forecast, e.g. health_score_sleep.
CATEGORY_TYPES = {category: f"health_score_{category}" for category in hs.CATEGORIES}


def clip(metric, value):
    _, _, lowest, highest = METRICS.get(metric, ("", "", 0.0, 100.0))  # categories are 0-100
    value = max(value, lowest)
    return min(value, highest) if highest is not None else value


def forecast(metric, level, slope, points, origin):
    """The fitted trend, the weekly history it came from, and its predictions.

    history is [(Monday of the week, value)]; each prediction's target_date is the Sunday
    ending that week.
    """
    return {
        "metric": metric, "level": clip(metric, level), "slope": slope, "weeks_of_data": len(points),
        "history": [(origin + timedelta(days=7 * t), value) for t, value in points],
        "predictions": [(origin + timedelta(days=7 * h + 6), clip(metric, level + slope * h))
                        for h in HORIZONS],
    }


def goal_weight_slope(profile, weight):
    """kg per week the user's fitness_goal expects when they do every planned workout."""
    if profile["fitness_goal"] == "lose_weight":
        return -WEIGHT_LOSS_PER_WEEK
    if profile["fitness_goal"] == "build_muscle":
        return weight * MUSCLE_GAIN_PER_MONTH[profile["fitness_level"]] / WEEKS_PER_MONTH
    return 0.0


def forecast_health(weeks, weights, origin):
    """The HealthScore forecast from weekly backend results, or None with no scored week.

    weeks is [(Monday, healthscore.build_result output)]. Each category is fit on its own, and
    every prediction is combined with hs.overall_score, which re-weights over the categories
    that have data, as the screen's provisional score does.
    """
    categories = {}
    for category in hs.CATEGORIES:
        points = [(week_index(monday, origin), r[category]) for monday, r in weeks if r[category] is not None]
        if points:
            categories[category] = forecast(CATEGORY_TYPES[category], *fit_trend(points, 0.0), points, origin)
    if not categories:
        return None
    level = hs.overall_score({c: f["level"] for c, f in categories.items()}, weights)
    predictions = [
        (target, hs.overall_score({c: f["predictions"][i][1] for c, f in categories.items()}, weights))
        for i, (target, _) in enumerate(next(iter(categories.values()))["predictions"])
    ]
    history = [(monday, r["overall_score"]) for monday, r in weeks if r["overall_score"] is not None]
    return {
        "metric": "health_score", "level": level, "slope": (predictions[-1][1] - level) / HORIZONS[-1],
        "weeks_of_data": len(history), "history": history, "predictions": predictions,
        "categories": categories, "weights": weights,
        "missing": [c for c in hs.CATEGORIES if c not in categories],
    }


def forecast_user(profile, history, today, workout_days=None, health=None, weight_model=None, use_ml=True):
    """Forecasts for one user, keyed by prediction_type. Metrics with no data are left out.

    profile is a raw Supabase profiles row; history maps body_measurements, workout_logs and
    activity_logs to that user's rows. workout_days is the planned workouts per week (the
    HealthScore's source: plan, then preferences, then onboarding); it defaults to the
    profile's workout_frequency. health is {"weeks": [(Monday, result)], "weights": {...}}
    from health_context, or None to skip the HealthScore. The weight forecast is corrected by
    weight_model (an XGBoost model from weight_forecast_model.py) or, when use_ml is true and none
    is given, by the saved model if one exists; use_ml=False gives the plain baseline.
    """
    origin = last_complete_week(today)
    workout_days = workout_days or profile["workout_frequency"]
    result = {}

    # Workouts: completed per week since the user joined, flat prior. Before a full week has
    # passed, the plan is the forecast.
    logs = history["workout_logs"]
    first_day = min([to_date(profile["created_at"])]
                    + [to_date(log["workout_date"]) for log in logs if log.get("workout_date")])
    points = weekly_workouts(logs, first_day, origin)
    if points:
        level, slope = fit_trend(points, 0.0)
    else:
        level, slope = float(workout_days), 0.0
    result["workouts_per_week"] = forecast("workouts_per_week", level, slope, points, origin)

    # Weight: body_measurements, or the onboarding weight until the user logs one. The goal's
    # expected rate is scaled by forecast adherence to the planned workouts.
    points = weekly_means(history["body_measurements"], "recorded_at", "weight_kg", origin)
    if not points and profile.get("weight_kg") is not None:
        points = [(min(week_index(to_date(profile["created_at"]), origin), 0), float(profile["weight_kg"]))]
    if points:
        next_week = result["workouts_per_week"]["predictions"][0][1]
        adherence = min(next_week / workout_days, 1.0)
        prior = goal_weight_slope(profile, points[-1][1]) * adherence
        level, slope = fit_trend(points, prior)
        slope = max(-MAX_WEEKLY_WEIGHT_CHANGE, min(slope, MAX_WEEKLY_WEIGHT_CHANGE))
        result["weight_kg"] = forecast("weight_kg", level, slope, points, origin)
        result["weight_kg"]["adherence"] = adherence

    points = weekly_means(history["activity_logs"], "log_date", "steps", origin)
    if points:
        result["daily_steps"] = forecast("daily_steps", *fit_trend(points, 0.0), points, origin)

    if use_ml and "weight_kg" in result:
        weight_model = weight_model or default_weight_model()
        if weight_model is not None:
            import weight_forecast_model

            weight_forecast_model.apply(weight_model, profile, result, origin)

    if health:
        health_score = forecast_health(health["weeks"], health["weights"], origin)
        if health_score:
            result["health_score"] = health_score
    return result


def default_weight_model():
    """The saved XGBoost weight model, or None until `python weight_forecast_model.py train` has run."""
    import weight_forecast_model

    return weight_forecast_model.load_model()


def forecast_rows(user_id, forecasts):
    """progress_forecasts rows for one user: one per metric and horizon."""
    results = list(forecasts.values()) + list(forecasts.get("health_score", {}).get("categories", {}).values())
    return [
        {"user_id": user_id, "prediction_type": result["metric"], "predicted_value": round(value, 2),
         "target_date": target.isoformat(), "model_version": result.get("model_version", MODEL_VERSION)}
        for result in results
        for target, value in result["predictions"]
    ]


HISTORY_TABLES = {
    # table: (columns, primary key)
    "body_measurements": ("user_id, recorded_at, weight_kg", "measurement_id"),
    "workout_logs": ("user_id, workout_date, completion_status", "workout_log_id"),
    "activity_logs": ("user_id, log_date, steps", "activity_id"),
}


def load_history(client, user_id=None):
    """{user_id: {table: rows}} for one user, or for everyone when user_id is None."""
    history = {}
    for table, (columns, key) in HISTORY_TABLES.items():
        for row in fetch_all(client, table, columns, key, user_id):
            history.setdefault(row["user_id"], {t: [] for t in HISTORY_TABLES})[table].append(row)
    return history


def health_context(client, profile, history, today):
    """Planned workout days and weekly HealthScore results, from the backend's HealthScore code.

    Weeks are scored from the earlier of sign-up and the first logged workout or activity, up
    to MAX_HEALTH_WEEKS complete weeks back.
    """
    from app import healthscore_repo as repo

    origin = last_complete_week(today)
    logged = [to_date(r["workout_date"]) for r in history["workout_logs"] if r.get("workout_date")]
    logged += [to_date(r["log_date"]) for r in history["activity_logs"] if r.get("log_date")]
    first = max(week_start(min([to_date(profile["created_at"])] + logged)),
                origin - timedelta(weeks=MAX_HEALTH_WEEKS - 1))
    weeks = []
    monday = first
    while monday <= origin:
        result, _ = repo.calculate(client, profile["user_id"], "week", monday + timedelta(days=6))
        weeks.append((monday, result))
        monday += timedelta(weeks=1)
    return {
        "workout_days": repo.workout_days_per_week(client, profile["user_id"], profile),
        "health": {"weeks": weeks, "weights": repo.active_weights(client)[0]},
    }


def forecast_from_supabase(client, user_id, today=None, context=health_context):
    today = today or datetime.now(timezone.utc).date()
    profiles = fetch_all(client, "profiles", "*", "user_id", user_id)
    if not profiles:
        raise LookupError(f"No profile found for user {user_id}.")
    history = load_history(client, user_id).get(user_id, {t: [] for t in HISTORY_TABLES})
    return forecast_user(profiles[0], history, today, **context(client, profiles[0], history, today))


def run_weekly(client, today=None, dry_run=False, context=health_context):
    """Forecast every user without forecasts from this week, and save them. Returns rows saved."""
    today = today or datetime.now(timezone.utc).date()
    this_week = week_start(today)
    done = {
        row["user_id"]
        for row in fetch_all(client, "progress_forecasts", "user_id, generated_at, model_version", "forecast_id")
        if row["model_version"] in (MODEL_VERSION, ML_MODEL_VERSION) and to_date(row["generated_at"]) >= this_week
    }
    history = load_history(client)
    rows = []
    for profile in fetch_all(client, "profiles", "*", "user_id"):
        if profile["user_id"] not in done:
            user_history = history.get(profile["user_id"], {t: [] for t in HISTORY_TABLES})
            extra = context(client, profile, user_history, today)
            rows += forecast_rows(profile["user_id"], forecast_user(profile, user_history, today, **extra))
    if rows and not dry_run:
        client.table("progress_forecasts").insert(rows).execute()
    return rows


def format_forecast(forecasts):
    corrected = "baseline_predictions" in forecasts.get("weight_kg", {})
    lines = ["\n--- Forecast (linear regression" + (" + XGBoost weight correction" if corrected else "")
             + ", refit weekly) ---"]
    for metric, (label, unit, _, _) in METRICS.items():
        result = forecasts.get(metric)
        if result is None:
            lines.append(f"{label}: no data yet")
            continue
        unit = f" {unit}" if unit else ""
        ahead = ", ".join(f"{value:.1f} in {h} wk" for h, (_, value) in zip(HORIZONS, result["predictions"]))
        weeks = result["weeks_of_data"]
        line = (f"{label}: {result['level']:.1f}{unit} now -> {ahead} "
                f"({result['slope']:+.2f}/wk, {weeks} {'week' if weeks == 1 else 'weeks'} of data)")
        if "adherence" in result:
            line += f"; assumes {result['adherence']:.0%} of planned workouts"
        lines.append(line)
        if "baseline_predictions" in result:
            base = ", ".join(f"{value:.1f}" for _, value in result["baseline_predictions"])
            lines.append(f"  Linear baseline alone: {base} kg; XGBoost moved it by "
                         + ", ".join(f"{fix:+.1f}" for fix in result["ml_corrections"]) + " kg")
        for category, part in result.get("categories", {}).items():
            lines.append(f"  {category.title()}: {part['level']:.0f} now -> "
                         f"{part['predictions'][-1][1]:.0f} in {HORIZONS[-1]} wk "
                         f"(weight {result['weights'][category]:.0%})")
        if result.get("missing"):
            lines.append(f"  Not logged yet: {', '.join(c.title() for c in result['missing'])}")
    return "\n".join(lines)


# The graph is styled like the website's HealthScore screen (src/index.css on
# feature/healthscore-ui): the night palette, VT323 pixel font, neon category frames and
# pixel-art icons.
THEME = {
    "night950": "#060a15", "night900": "#0a1122", "night800": "#10192f", "night700": "#18233f",
    "night600": "#26345a", "night500": "#3a4a78", "ink": "#e8edff", "muted": "#94a3c8",
    "gold": "#f7b733", "cyan": "#4fd8ff",
}
CATEGORY_COLORS = {"nutrition": "#ff5d6c", "workouts": "#4d8dff", "activity": "#42e08b", "sleep": "#a66bff"}
# Each metric's frame color and icon. HealthScore gets the screen's gold trophy.
PANELS = {
    "weight_kg": (THEME["cyan"], "kettlebell"),
    "workouts_per_week": (CATEGORY_COLORS["workouts"], "dumbbell"),
    "daily_steps": (CATEGORY_COLORS["activity"], "runner"),
    "health_score": (THEME["gold"], "trophy"),
}
CATEGORY_ICONS = {"nutrition": "apple", "workouts": "dumbbell", "activity": "runner", "sleep": "moon"}
# Pixel art copied from src/icons.js on feature/healthscore-ui. One character per pixel; "." is clear.
ICONS = {
    "trophy": {
        "colors": {"y": "#f7b733", "o": "#c4831a", "w": "#fff1c4", "b": "#8a5a32"},
        "art": [
            "..yyyyyyyy..",
            "yyywyyyyyoyy",
            "y.ywyyyyyo.y",
            "y.ywyyyyyo.y",
            ".yyyyyyyoyy.",
            "...yyyyoo...",
            "....yyoo....",
            ".....yo.....",
            ".....yo.....",
            "...oooooo...",
            "...bbbbbb...",
            "..bbbbbbbb..",
        ],
    },
    "kettlebell": {
        "colors": {"k": "#94a3c8", "d": "#5d6b91", "w": "#e8edff"},
        "art": [
            "...kkkkkk...",
            "..kk....kk..",
            "..k......k..",
            "..kk....kk..",
            ".kkkkkkkkkk.",
            "kkwkkkkkkkkk",
            "kwkkkkkkkkkk",
            "kkkkkkkkkkkd",
            "kkkkkkkkkkdd",
            ".kkkkkkkddd.",
            "..dddddddd..",
        ],
    },
    "dumbbell": {
        "colors": {"b": "#4d8dff", "d": "#2c5fc4", "l": "#b9cdf0"},
        "art": [
            ".bb......bb.",
            "bbbb....bbbb",
            "bbbb....bbbb",
            "bbbbllllbbbb",
            "bbbbllllbbbb",
            "dddd....dddd",
            "dddd....dddd",
            ".dd......dd.",
        ],
    },
    "runner": {
        "colors": {"g": "#42e08b", "d": "#22a862"},
        "art": [
            "......gg....",
            "......gg....",
            "...ggggg....",
            "..g..ggg.gg.",
            ".g...gg.....",
            ".....ggg....",
            "....gg.gg...",
            "...gg...dd..",
            "..dd.....d..",
            ".dd......d..",
            "dd.......dd.",
        ],
    },
    "apple": {
        "colors": {"r": "#ff5d6c", "d": "#c23447", "w": "#ffd1d6", "g": "#42e08b", "b": "#8a5a32"},
        "art": [
            "......b.gg..",
            "......bggg..",
            "...rr.b.rr..",
            "..rrrrrrrrr.",
            ".rwwrrrrrrrr",
            ".rwrrrrrrrrr",
            ".rrrrrrrrrrr",
            ".rrrrrrrrrrd",
            ".rrrrrrrrrdd",
            "..rrrrrrrdd.",
            "...rrd.rdd..",
        ],
    },
    "moon": {
        "colors": {"p": "#a66bff", "d": "#7443c9", "s": "#e0ccff"},
        "art": [
            "....ppp.....",
            "..pppp....s.",
            ".ppp.......",
            ".ppp.......s",
            "pppp........",
            "pppp........",
            "pppd........",
            "pppdd.......",
            ".pppdd....d.",
            ".ppppddddd..",
            "..pppppdd...",
            "....ppp.....",
        ],
    },
}
FONT_PATH = BASE_DIR / "assets" / "fonts" / "VT323-Regular.ttf"  # SIL Open Font License, see VT323-LICENSE.txt
CHART_FORMAT = {"weight_kg": "{:.1f}", "workouts_per_week": "{:.1f}", "daily_steps": "{:,.0f}",
                "health_score": "{:.0f}"}
SLOPE_UNITS = {"weight_kg": "kg", "workouts_per_week": "workouts", "daily_steps": "steps",
               "health_score": "points"}
EMPTY_HINTS = {"weight_kg": "Log a weight in body_measurements.",
               "workouts_per_week": "Log a workout.",
               "daily_steps": "Log steps in activity_logs.",
               "health_score": "Log workouts, meals, sleep or activity."}


def chart_lines(result):
    """(logged, forecast) points to draw, as [(date, value)]; forecast points sit at each week's Monday.

    The dashed forecast continues from the last logged week, or from the fitted level when
    nothing is logged yet.
    """
    origin = result["predictions"][0][0] - timedelta(days=13)  # Monday of the last complete week
    future = [(target - timedelta(days=6), value) for target, value in result["predictions"]]
    logged = list(result["history"])
    if not logged:
        return logged, [(origin, result["level"])] + future
    start = [] if logged[-1][0] == origin else [(origin, result["level"])]
    return logged, [logged[-1]] + start + future


def y_limits(metric, values):
    lo, hi = min(values), max(values)
    # A flat line (allowing for float noise) gets a band around it instead of a zero-height axis.
    pad = max(abs(hi) * 0.05, 1.0) if hi - lo <= 1e-9 * max(1.0, abs(hi)) else (hi - lo) * 0.15
    lo = lo - pad if metric == "weight_kg" else max(0.0, lo - pad)
    hi = min(100.0, hi + pad) if metric == "health_score" else hi + pad
    # A little room below a zero floor, so points at 0 aren't cut in half by the axis.
    return (lo - (hi - lo) * 0.04 if lo == 0.0 else lo), hi


def pixel_font(size):
    from matplotlib.font_manager import FontProperties

    return FontProperties(fname=FONT_PATH, size=size)


def draw_icon(fig, name, x, y, height):
    """Draw a pixel icon with its bottom-left corner at (x, y), in figure coordinates.

    Returns the icon's right edge, so text can follow it.
    """
    from matplotlib.colors import to_rgba

    icon = ICONS[name]
    width = max(len(row) for row in icon["art"])
    pixels = np.zeros((len(icon["art"]), width, 4))
    for r, row in enumerate(icon["art"]):
        for c, ch in enumerate(row):
            if ch in icon["colors"]:
                pixels[r, c] = to_rgba(icon["colors"][ch])
    fig_w, fig_h = fig.get_size_inches()
    icon_width = height * fig_h / fig_w * width / len(icon["art"])
    ax = fig.add_axes((x, y, icon_width, height))
    ax.imshow(pixels, interpolation="nearest")
    ax.set_axis_off()
    return x + icon_width


def wrap_parts(fig, parts, font, max_width, sep=".  "):
    """Join parts into lines no wider than max_width (figure coordinates), breaking between parts."""
    renderer = fig.canvas.get_renderer()

    def width(text):
        probe = fig.text(0, 0, text, fontproperties=font)
        size = probe.get_window_extent(renderer).width / fig.bbox.width
        probe.remove()
        return size

    lines = [parts[0]]
    for part in parts[1:]:
        if width(lines[-1] + sep + part + ".") <= max_width:
            lines[-1] += sep + part
        else:
            lines.append(part)
    return "\n".join(line + "." for line in lines)


def draw_frame(fig, box, color):
    """A dark panel with a 3px neon border and a soft glow, like the screen's category cards."""
    from matplotlib.patches import Rectangle

    x, y, w, h = box
    fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, facecolor=THEME["night800"],
                             alpha=0.92, lw=0, zorder=0))
    for width, alpha in ((14, 0.05), (8, 0.10), (4.5, 1.0)):  # glow first, then the crisp border
        fig.add_artist(Rectangle((x, y), w, h, transform=fig.transFigure, fill=False, edgecolor=color,
                                 lw=width, alpha=alpha, joinstyle="miter", zorder=1))


def draw_backdrop(fig):
    """Night sky: seeded stars, and a stepped mountain and pine ridge along the bottom."""
    from matplotlib.patches import Rectangle

    sky = fig.add_axes((0, 0, 1, 1), zorder=-10)
    sky.set_xlim(0, 320)
    sky.set_ylim(0, 240)
    sky.set_axis_off()
    sky.add_patch(Rectangle((0, 0), 320, 240, color=THEME["night950"], lw=0))
    rand = np.random.default_rng(7)
    for _ in range(90):
        size = rand.choice([0.8, 0.8, 1.2, 1.8])
        sky.add_patch(Rectangle((rand.uniform(0, 320), rand.uniform(30, 240)), size, size, lw=0,
                                color=THEME["ink"] if size > 1.5 else THEME["muted"], alpha=rand.uniform(0.25, 0.8)))
    for base, amp, step, color in ((46, 9, 8, THEME["night800"]), (30, 6, 5, THEME["night900"])):
        height = base
        for x in range(0, 320, step):
            height = max(base - amp * 2, min(base + amp, height + rand.uniform(-0.5, 0.5) * amp))
            sky.add_patch(Rectangle((x, 0), step, round(height), color=color, lw=0))


def draw_metric(fig, box, metric, result):
    import matplotlib.dates as mdates
    import matplotlib.patheffects as pe
    import matplotlib.ticker as mticker

    color, icon = PANELS[metric]
    label, unit, _, _ = METRICS[metric]
    x, y, w, h = box
    draw_frame(fig, box, color)
    left, top = x + 0.022, y + h - 0.028
    icon_right = draw_icon(fig, icon, left, top - 0.04, 0.04)
    fig.text(icon_right + 0.012, top - 0.022, label, color=color, fontproperties=pixel_font(26), va="center")
    if result is None:
        fig.text(x + w / 2, y + h / 2 - 0.02, f"No data yet.\n{EMPTY_HINTS[metric]}", ha="center", va="center",
                 color=THEME["muted"], fontproperties=pixel_font(19), linespacing=1.4)
        return

    fmt = CHART_FORMAT[metric].format
    end = result["predictions"][-1][1]
    slope = result["slope"]
    sign = "+" if slope > 0 else "−" if slope < 0 else "±"
    amount = f"{abs(slope):,.0f}" if metric == "daily_steps" else f"{abs(slope):.2f}"
    big = fig.text(left, top - 0.088, fmt(end), color=THEME["ink"], fontproperties=pixel_font(46), va="baseline")
    fig.canvas.draw()  # measure the big number so the rest of the line sits right after it
    big_right = big.get_window_extent().transformed(fig.transFigure.inverted()).x1
    suffix = "/100" if metric == "health_score" else unit
    fig.text(big_right + 0.006, top - 0.088, f"{suffix}  in {HORIZONS[-1]} weeks  ·  {sign}{amount} {SLOPE_UNITS[metric]}/wk",
             color=THEME["muted"], fontproperties=pixel_font(19), va="baseline")
    notes = [f"Now {fmt(result['level'])}", f"{result['weeks_of_data']} "
             f"{'week' if result['weeks_of_data'] == 1 else 'weeks'} of data"]
    if result["weeks_of_data"] < 4:
        notes.append("trend mostly from the profile" if metric in ("weight_kg", "workouts_per_week")
                     else "trend held back until 4 weeks")
    if "adherence" in result:
        notes.append(f"assumes {result['adherence']:.0%} of planned workouts")
    if result.get("missing"):
        notes.append("provisional")
    note_text = wrap_parts(fig, notes, pixel_font(16), w - 0.045)
    fig.text(left, top - 0.104, note_text, color=THEME["muted"], fontproperties=pixel_font(16), va="top",
             linespacing=1.25)
    note_room = 0.02 * note_text.count("\n")  # a wrapped note pushes the plot down

    legend_room = 0.085 if metric == "health_score" else 0.0
    ax = fig.add_axes((x + 0.06, y + 0.04 + legend_room, w - 0.115, h - 0.205 - legend_room - note_room))
    ax.set_facecolor("none")
    logged, future = chart_lines(result)
    origin = result["predictions"][0][0] - timedelta(days=13)  # Monday of the last complete week
    lo, hi = y_limits(metric, [v for _, v in logged + future])
    ax.axvspan(origin, future[-1][0] + timedelta(days=4), color=THEME["night700"], alpha=0.7, lw=0)
    ax.axvline(origin, color=THEME["night500"], lw=2)
    # Inside the shaded area, at whichever end the forecast line stays away from.
    low_line = min(v for _, v in future) < lo + (hi - lo) * 0.25
    ax.text(origin + timedelta(days=3), 0.96 if low_line else 0.04, "FORECAST",
            transform=ax.get_xaxis_transform(), color=THEME["muted"], fontproperties=pixel_font(15),
            va="top" if low_line else "bottom")

    glow = [pe.Stroke(linewidth=9, foreground=color, alpha=0.18), pe.Normal()]
    if logged:
        ax.plot([d for d, _ in logged], [v for _, v in logged], color=color, lw=3, solid_capstyle="butt",
                solid_joinstyle="miter", marker="s", ms=8, mfc=color, mec=THEME["night800"], mew=1.5,
                zorder=3, path_effects=glow)
    ax.plot([d for d, _ in future], [v for _, v in future], color=color, lw=3, ls=(0, (2, 1.5)),
            dash_capstyle="butt", zorder=2, path_effects=glow)
    forecast_points = future[-len(HORIZONS):]
    ax.plot([d for d, _ in forecast_points], [v for _, v in forecast_points], ls="none", marker="s", ms=9,
            mfc=THEME["night800"], mec=color, mew=2.5, zorder=4)
    ax.annotate(fmt(end), (future[-1][0], end), xytext=(10, 0), textcoords="offset points", va="center",
                color=THEME["ink"], fontproperties=pixel_font(20))

    ax.set_ylim(lo, hi)
    ax.set_xlim(min([origin - timedelta(weeks=4)] + [d for d, _ in logged]) - timedelta(days=3),
                future[-1][0] + timedelta(days=4))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(4))
    if metric == "daily_steps":
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1000:g}K" if v >= 1000 else f"{v:g}"))
    ax.grid(axis="y", color=THEME["night600"], lw=1.2)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(THEME["night500"])
    ax.spines["bottom"].set_linewidth(2)
    ax.tick_params(colors=THEME["muted"], length=0, pad=6)
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontproperties(pixel_font(16))

    if metric == "health_score":
        # The screen's four category cards, in its order: icon, name in its color, now -> 12 weeks.
        for i, category in enumerate(("nutrition", "workouts", "activity", "sleep")):
            cx = x + 0.025 + (i % 2) * (w / 2 - 0.01)
            cy = y + 0.05 - (i // 2) * 0.028
            draw_icon(fig, CATEGORY_ICONS[category], cx, cy - 0.003, 0.02)
            fig.text(cx + 0.032, cy, category.title(), color=CATEGORY_COLORS[category],
                     fontproperties=pixel_font(16), va="bottom")
            part = result["categories"].get(category)
            detail = (f"{part['level']:.0f} to {part['predictions'][-1][1]:.0f} "
                      f"({result['weights'][category]:.0%})" if part else "not logged yet")
            fig.text(cx + 0.096, cy, detail, color=THEME["ink"] if part else THEME["muted"],
                     fontproperties=pixel_font(16), va="bottom")


def write_chart(user_id, forecasts, name=None, folder=None):
    """Save <folder>/forecast-<user_id>.png (default charts/): one panel per metric, logged weeks
    solid, forecast dashed. Returns the path."""
    import matplotlib

    matplotlib.use("Agg")  # draw to a file; no window
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(14, 11), facecolor=THEME["night950"])
    draw_backdrop(fig)
    draw_icon(fig, "trophy", 0.035, 0.945, 0.032)
    fig.text(0.066, 0.961, "FITSENSE", color=THEME["ink"], fontproperties=pixel_font(30), va="center")
    fig.text(0.035, 0.875, "Progress Forecast", color=THEME["ink"], fontproperties=pixel_font(64), va="baseline")
    # "player" for users without a name, as the website's login screen greets them.
    parts = [f"Your next {HORIZONS[-1]} weeks, {name or 'player'}", "Solid: logged weeks",
             "Dashed: forecast, refit every week with linear regression"]
    fig.text(0.037, 0.862, wrap_parts(fig, parts, pixel_font(20), 0.93, sep=". "), va="top",
             color=THEME["muted"], fontproperties=pixel_font(20))
    gap, left, bottom, top = 0.025, 0.035, 0.035, 0.81
    width, height = (1 - 2 * left - gap) / 2, (top - bottom - gap) / 2
    for i, metric in enumerate(METRICS):
        box = (left + (i % 2) * (width + gap), top - (i // 2 + 1) * height - (i // 2) * gap, width, height)
        draw_metric(fig, box, metric, forecasts.get(metric))
    path = Path(folder or BASE_DIR / "charts") / f"forecast-{user_id}.png"
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=THEME["night950"])
    plt.close(fig)
    return path


def open_in_vscode(path):
    """Open the file as a tab in the current VS Code window; False when the `code` command is missing."""
    import shutil
    import subprocess

    code = shutil.which("code")
    if code is None:
        return False
    subprocess.run([code, "--reuse-window", str(path)], check=False)
    return True


def main():
    import importlib.util

    spec = importlib.util.spec_from_file_location("recommender", BASE_DIR / "Fitsense-Issue-5.py")
    recommender = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recommender)

    if sys.argv[1:2] == ["weekly"]:
        dry_run = "--dry-run" in sys.argv
        rows = run_weekly(recommender.supabase_client(), dry_run=dry_run)
        print(f"{'Would save' if dry_run else 'Saved'} {len(rows)} forecasts to progress_forecasts.")
    elif "--user" in sys.argv and sys.argv.index("--user") + 1 < len(sys.argv):
        user_id = sys.argv[sys.argv.index("--user") + 1]
        client = recommender.supabase_client()
        forecasts = forecast_from_supabase(client, user_id)
        name = (fetch_all(client, "profiles", "user_id, name", "user_id", user_id)[0].get("name"))
        path = write_chart(user_id, forecasts, name)
        print(format_forecast(forecasts))
        print(f"\nGraph: {path}")
        if "--no-open" not in sys.argv and not open_in_vscode(path):
            print("Open it in VS Code to view it (the `code` command isn't on PATH).")
    else:
        print("Usage: python progress_forecast.py --user <user_id> [--no-open] | weekly [--dry-run]")


if __name__ == "__main__":
    main()
