// Turns the backend's HealthScore response (GET /healthscore/{user_id}) into
// what the HealthScore screen shows: scores, notes and empty states.

export const RANGES = [
  { id: "week", label: "Last 7 Days" },
  { id: "last-week", label: "Previous 7 Days" },
  { id: "month", label: "Last 30 Days" },
];

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

// One line under each category score, built from the backend's details.
const NOTES = {
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

const EMPTY_NOTES = {
  no_workout_plan: "Set your workout days to track this.",
  no_workouts_logged: "No workouts logged yet.",
  no_nutrition_targets: "Set a nutrition goal to track this.",
  not_enough_meals_logged: (d) => `Log meals on ${plural(d.days_needed, "day")} to unlock (${d.days_logged} so far).`,
  no_sleep_logged: "No sleep logged yet.",
  no_activity_logged: "No steps or active minutes logged yet.",
};

function note(key, details) {
  if (details.available) return NOTES[key](details);
  const empty = EMPTY_NOTES[details.reason];
  return typeof empty === "function" ? empty(details) : empty ?? "Not enough data yet.";
}

export function toViewModel(result) {
  const scores = Object.fromEntries(
    CATEGORIES.map((c) => {
      const details = result.categories[c.key];
      return [c.key, { score: details.score, available: details.available, note: note(c.key, details) }];
    })
  );
  return {
    overall: result.overall_score,
    provisional: result.provisional,
    missing: CATEGORIES.filter((c) => !scores[c.key].available).map((c) => c.label),
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
