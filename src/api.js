// FitSense backend (FastAPI) client. Set VITE_API_URL in .env to point elsewhere.

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the FitSense server. Is the backend running?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.detail);
  return data;
}

// The user's local date (YYYY-MM-DD), so "this week" matches their calendar.
export function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Testing login: returns { user_id, username, has_profile }.
export const signup = (username, password) => request("POST", "/auth/signup", { username, password });
export const login = (username, password) => request("POST", "/auth/login", { username, password });

export const saveProfile = (userId, profile) => request("PUT", `/profiles/${userId}`, profile);
export const getProfile = (userId) => request("GET", `/profiles/${userId}`);
export const getHealthScore = (userId, range) =>
  request("GET", `/healthscore/${userId}?range=${encodeURIComponent(range)}&end_date=${localToday()}`);

// Logging: each one feeds a HealthScore category.
export const logWorkout = (userId, workoutDate, completionStatus, durationMinutes) =>
  request("POST", `/logs/${userId}/workouts`, {
    workout_date: workoutDate,
    completion_status: completionStatus,
    duration_minutes: durationMinutes ?? null,
  });
export const logSleep = (userId, date, hoursSlept) =>
  request("PUT", `/logs/${userId}/sleep/${date}`, { hours_slept: hoursSlept });
export const logActivity = (userId, date, steps) => request("PUT", `/logs/${userId}/activity/${date}`, { steps });
export const logMeal = (userId, meal) => request("POST", `/logs/${userId}/meals`, meal);
export const getGoals = (userId) => request("GET", `/goals/${userId}`);

// Food logging: describe a meal -> review the estimate -> confirm.
export const analyzeMeal = (userId, text, logDate, mealType) =>
  request("POST", `/meals/${userId}/analyze`, { text, log_date: logDate, meal_type: mealType || null });
export const listMeals = (userId, logDate, status) =>
  request("GET", `/meals?user_id=${userId}&log_date=${logDate}${status ? `&status=${status}` : ""}`);
export const updateMealItem = (mealId, itemId, changes) => request("PATCH", `/meals/${mealId}/items/${itemId}`, changes);
export const addMealItem = (mealId, text) => request("POST", `/meals/${mealId}/items`, { text });
export const deleteMealItem = (mealId, itemId) => request("DELETE", `/meals/${mealId}/items/${itemId}`);
export const confirmMeal = (mealId) => request("POST", `/meals/${mealId}/confirm`);
export const discardMeal = (mealId) => request("POST", `/meals/${mealId}/discard`);
export const searchFoods = (q) => request("GET", `/foods/search?q=${encodeURIComponent(q)}`);

// First readable validation message from a 422, for forms.
export function validationMessage(error, fallback = "Something went wrong. Please try again.") {
  if (error.status === 422 && Array.isArray(error.detail)) {
    const d = error.detail[0];
    const field = d.loc?.at(-1);
    return field && typeof field === "string" ? `${field.replace(/_/g, " ")}: ${d.msg}` : d.msg;
  }
  return error.status === 0 || typeof error.detail === "string" ? error.message : fallback;
}

// --- Converting between the onboarding screens and the API ----------------------

const LB_TO_KG = 0.45359237;
const IN_TO_CM = 2.54;

const GOALS = {
  "Lose Weight": "lose_weight",
  "Build Muscle": "build_muscle",
  Endurance: "improve_endurance",
  "General Fitness": "general_fitness",
};
const LOCATIONS = { Home: "home", Gym: "gym", Both: "mixed" };
const invert = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [v, k]));
const capitalize = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

const round1 = (n) => Math.round(n * 10) / 10;

// Onboarding answers (lbs, ft/in, display labels) -> API profile (kg, cm, enum values)
export function toApiProfile(p) {
  const totalInches = Number(p.feet) * 12 + (Number(p.inches) || 0);
  return {
    name: p.name.trim() || null,
    age: Number(p.age),
    height_cm: round1(totalInches * IN_TO_CM),
    weight_kg: round1(Number(p.weight) * LB_TO_KG),
    fitness_goal: GOALS[p.goal],
    fitness_level: p.proficiency.toLowerCase(),
    workout_frequency: Number(p.workoutDays),
    workout_location: LOCATIONS[p.workoutLocation],
    workout_preferences: [],
  };
}

// API profile -> onboarding answers, for showing and editing a saved profile
export function fromApiProfile(p) {
  const totalInches = Math.round(p.height_cm / IN_TO_CM);
  return {
    name: p.name ?? "",
    age: String(p.age),
    weight: String(Math.round(p.weight_kg / LB_TO_KG)),
    feet: String(Math.floor(totalInches / 12)),
    inches: String(totalInches % 12),
    goal: invert(GOALS)[p.fitness_goal] ?? "General Fitness",
    proficiency: capitalize(p.fitness_level),
    workoutDays: String(p.workout_frequency),
    workoutLocation: invert(LOCATIONS)[p.workout_location] ?? "Both",
  };
}

// Turn a 422 from /profiles into something a player can act on.
const FIELD_HINTS = {
  age: "Age must be between 13 and 100.",
  height_cm: "Height must be between 3 ft 4 in and 8 ft 2 in.",
  weight_kg: "Weight must be between 66 and 660 lbs.",
  workout_frequency: "Workout days must be between 1 and 7.",
};

export function profileErrorMessage(error) {
  if (error.status === 422 && Array.isArray(error.detail)) {
    const field = error.detail.map((d) => d.loc?.at(-1)).find((f) => FIELD_HINTS[f]);
    if (field) return FIELD_HINTS[field];
    return "Some of your answers look off. Go back and check them.";
  }
  if (error.status === 0) return error.message;
  return "Couldn't save your profile. Please try again.";
}
