// Turns the backend's HealthScore response (GET /healthscore/{user_id}) into
// what the HealthScore screen shows: scores, notes and empty states.
// The screen shows one day at a time; week/month windows are still supported for other views.

// Colours from the HealthScore spec: blue workouts, coral nutrition,
// purple sleep, green activity.
export const CATEGORIES = [
  { key: "nutrition", label: "Nutrition", color: "#ff5d6c", shades: ["#ffd1d6", "#ff8f9b", "#ff5d6c"] },
  { key: "workouts", label: "Workouts", color: "#4d8dff", shades: ["#d6e4ff", "#8fb6ff", "#4d8dff"] },
  { key: "activity", label: "Activity", color: "#42e08b", shades: ["#d1ffe6", "#86f0b6", "#42e08b"] },
  { key: "sleep", label: "Sleep", color: "#a66bff", shades: ["#eadbff", "#c7a2ff", "#a66bff"] },
];

const num = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 1 });
const plural = (n, word) => `${num(n)} ${word}${n === 1 ? "" : "s"}`;
const shortDate = (iso) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
const weekSoFar = (d) => `${num(d.done_earlier_this_week)} of ${plural(d.planned_per_week, "workout")} done earlier this week.`;

// One line under each category score for a single day.
const DAY_NOTES = {
  workouts: (d) =>
    d.status === "missed"
      ? `No workout, and this week's plan no longer fits without it. ${weekSoFar(d)}`
      : `Workout ${d.status}. ${weekSoFar(d)}`,
  nutrition: (d) =>
    `${num(d.average.calories)} of ${num(d.targets.calories)} kcal and ${num(d.average.protein_g)} of ${num(
      d.targets.protein_g
    )} g protein${d.targets_estimated ? " (estimated targets)" : ""}.`,
  sleep: (d) =>
    `${num(d.average_hours)} of ${num(d.target_hours)} hours, night of ${shortDate(d.night_of)}${
      d.sleep_quality ? `, quality ${d.sleep_quality}/5` : ""
    }.`,
  activity: (d) =>
    d.average_steps != null
      ? `${num(d.average_steps)} of ${num(d.steps_target)} steps.`
      : `${num(d.average_active_minutes)} of ${num(d.active_minutes_target)} active minutes.`,
};

const DAY_EMPTY = {
  rest_day: (d) => `Rest day. ${weekSoFar(d)}`,
  before_signup: "Before you joined.",
  not_enough_meals_logged: "No meals logged this day.",
  no_sleep_logged: "No sleep logged for the night before.",
  no_activity_logged: "No steps or active minutes logged.",
};

// Notes for a multi-day window.
const WINDOW_NOTES = {
  workouts: (d) => `${num(d.completed)} of ${plural(d.scheduled, "planned workout")} completed.`,
  nutrition: (d) =>
    `${num(d.average.calories)} of ${num(d.targets.calories)} kcal and ${num(d.average.protein_g)} of ${num(
      d.targets.protein_g
    )} g protein per day${d.targets_estimated ? " (estimated targets)" : ""}.`,
  sleep: (d) => `${num(d.average_hours)} of ${num(d.target_hours)} hours per night on average.`,
  activity: (d) =>
    d.average_steps != null
      ? `${num(d.average_steps)} of ${num(d.steps_target)} steps per day on average.`
      : `${num(d.average_active_minutes)} of ${num(d.active_minutes_target)} active minutes per day.`,
};

const WINDOW_EMPTY = {
  no_workouts_logged: "No workouts logged yet.",
  not_enough_meals_logged: (d) => `Log meals on ${plural(d.days_needed, "day")} to unlock (${d.days_logged} so far).`,
  no_sleep_logged: "No sleep logged yet.",
  no_activity_logged: "No steps or active minutes logged yet.",
};

const COMMON_EMPTY = {
  no_workout_plan: "Set your workout days to track this.",
  no_nutrition_targets: "Set a nutrition goal to track this.",
};

function note(key, details, isDay) {
  if (details.available) return (isDay ? DAY_NOTES : WINDOW_NOTES)[key](details);
  const empty = (isDay ? DAY_EMPTY : WINDOW_EMPTY)[details.reason] ?? COMMON_EMPTY[details.reason];
  return typeof empty === "function" ? empty(details) : empty ?? "Not enough data yet.";
}

const NOT_EXPECTED = ["rest_day", "before_signup"];

export function toViewModel(result) {
  const isDay = result.range?.key === "day";
  const scores = Object.fromEntries(
    CATEGORIES.map((c) => {
      const details = result.categories[c.key];
      return [c.key, { score: details.score, available: details.available, note: note(c.key, details, isDay) }];
    })
  );
  return {
    overall: result.overall_score,
    provisional: result.provisional,
    // a rest day isn't missing data
    missing: CATEGORIES.filter((c) => !scores[c.key].available && !NOT_EXPECTED.includes(result.categories[c.key].reason))
      .map((c) => c.label),
    disclaimer: result.disclaimer,
    scores,
  };
}

export function scoreLabel(score) {
  if (score == null) return "Start Logging!";
  if (score >= 90) return "Legendary!";
  if (score >= 80) return "Great Progress!";
  if (score >= 65) return "Keep Going!";
  return "Level Up Time!";
}
