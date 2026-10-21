// PLACEHOLDER HealthScore data until the backend computes real scores from
// logged nutrition, workouts, activity and sleep. Only the workout note uses
// the player's onboarding answers (planned days per week).

export const RANGES = [
  { id: "week", label: "This Week" },
  { id: "last-week", label: "Last Week" },
  { id: "month", label: "This Month" },
];

const SAMPLE = {
  week: {
    nutrition: { score: 78, note: "Good macronutrient balance this week." },
    workouts: { score: 85, completedRatio: 0.75 },
    activity: { score: 80, note: "7,500 average steps per day." },
    sleep: { score: 86, note: "7.8 hours average per night." },
  },
  "last-week": {
    nutrition: { score: 71, note: "A few high-sugar days to watch." },
    workouts: { score: 92, completedRatio: 1 },
    activity: { score: 74, note: "6,200 average steps per day." },
    sleep: { score: 79, note: "7.1 hours average per night." },
  },
  month: {
    nutrition: { score: 75, note: "Protein goal hit on 19 of 30 days." },
    workouts: { score: 81, completedRatio: 0.7 },
    activity: { score: 83, note: "8,100 average steps per day." },
    sleep: { score: 84, note: "7.6 hours average per night." },
  },
};

export const CATEGORIES = [
  { key: "nutrition", label: "Nutrition", color: "#ff5d6c", shades: ["#ffd1d6", "#ff8f9b", "#ff5d6c"] },
  { key: "workouts", label: "Workouts", color: "#4d8dff", shades: ["#d6e4ff", "#8fb6ff", "#4d8dff"] },
  { key: "activity", label: "Activity", color: "#42e08b", shades: ["#d1ffe6", "#86f0b6", "#42e08b"] },
  { key: "sleep", label: "Sleep", color: "#a66bff", shades: ["#eadbff", "#c7a2ff", "#a66bff"] },
];

export function getHealthScore(rangeId, { workoutDays }) {
  const data = SAMPLE[rangeId] ?? SAMPLE.week;
  const weeks = rangeId === "month" ? 4 : 1;
  const planned = (Number(workoutDays) || 4) * weeks;
  const completed = Math.round(planned * data.workouts.completedRatio);

  const scores = {
    nutrition: data.nutrition,
    workouts: { score: data.workouts.score, note: `${completed} of ${planned} planned workouts completed.` },
    activity: data.activity,
    sleep: data.sleep,
  };

  const overall = Math.round(
    CATEGORIES.reduce((sum, c) => sum + scores[c.key].score, 0) / CATEGORIES.length
  );

  return { overall, scores };
}

export function scoreLabel(score) {
  if (score >= 90) return "Legendary!";
  if (score >= 80) return "Great Progress!";
  if (score >= 65) return "Keep Going!";
  return "Level Up Time!";
}
