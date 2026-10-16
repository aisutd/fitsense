import { useState } from "react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";
import MealLogger from "./MealLogger";
import { localToday, logActivity, logMeal, logSleep, logWorkout, validationMessage } from "../api";

// Quick logging on the HealthScore page. Each tab feeds one category; after a
// successful log the page refreshes the score.

const TABS = [
  { id: "workout", label: "Workout", icon: ICONS.dumbbell, color: "#4d8dff" },
  { id: "sleep", label: "Sleep", icon: ICONS.moon, color: "#a66bff" },
  { id: "steps", label: "Steps", icon: ICONS.runner, color: "#42e08b" },
  { id: "meal", label: "Meal", icon: ICONS.apple, color: "#ff5d6c" },
];

const STATUSES = [
  { id: "completed", label: "Completed" },
  { id: "partial", label: "Partial" },
  { id: "skipped", label: "Skipped" },
];

const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"];

function Field({ label, suffix, ...props }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm uppercase tracking-wider text-muted">{label}</span>
      <span className="px-frame flex items-center gap-2 bg-night-900/80 px-3 py-1 focus-within:[--frame:var(--color-cyan)]">
        <input className="w-full min-w-0 bg-transparent py-1 text-xl text-ink outline-none [color-scheme:dark]" {...props} />
        {suffix && <span className="shrink-0 text-muted">{suffix}</span>}
      </span>
    </label>
  );
}

const num = (v) => (v === "" ? NaN : Number(v));

function LogPanel({ userId, onLogged }) {
  const today = localToday();
  const [tab, setTab] = useState("workout");
  const [date, setDate] = useState(today);
  const [status, setStatus] = useState("completed");
  const [duration, setDuration] = useState("");
  const [hours, setHours] = useState("");
  const [steps, setSteps] = useState("");
  const [meal, setMeal] = useState({ meal_type: "lunch", display_name: "", calories: "", protein_g: "", carbs_g: "", fat_g: "" });
  const [busy, setBusy] = useState(false);
  const [manualMeal, setManualMeal] = useState(false);
  const [message, setMessage] = useState(null); // { ok, text }

  const active = TABS.find((t) => t.id === tab);
  const setMealField = (key) => (e) => setMeal((m) => ({ ...m, [key]: e.target.value }));

  const valid = {
    workout: !!date,
    sleep: !!date && num(hours) >= 0 && num(hours) <= 24,
    steps: !!date && Number.isInteger(num(steps)) && num(steps) >= 0,
    meal: !!date && ["calories", "protein_g", "carbs_g", "fat_g"].every((k) => num(meal[k]) >= 0),
  }[tab];

  async function submit(event) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setMessage(null);
    try {
      if (tab === "workout") {
        await logWorkout(userId, date, status, duration === "" ? null : num(duration));
      } else if (tab === "sleep") {
        await logSleep(userId, date, num(hours));
      } else if (tab === "steps") {
        await logActivity(userId, date, num(steps));
      } else {
        await logMeal(userId, {
          log_date: date,
          meal_type: meal.meal_type,
          display_name: meal.display_name.trim() || null,
          calories: num(meal.calories),
          protein_g: num(meal.protein_g),
          carbs_g: num(meal.carbs_g),
          fat_g: num(meal.fat_g),
        });
      }
      setMessage({ ok: true, text: `${active.label} logged. HealthScore updated.` });
      onLogged();
    } catch (error) {
      setMessage({ ok: false, text: validationMessage(error, "Couldn't save that. Please try again.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="px-frame mt-14 bg-night-800/85 p-6 sm:p-8" aria-labelledby="log-title">
      <h2 id="log-title" className="text-2xl font-bold">
        Log Progress
      </h2>
      <p className="mt-1 text-muted">Add a workout, sleep, steps or a meal and watch your HealthScore change.</p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4" role="tablist" aria-label="What to log">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              setTab(t.id);
              setMessage(null);
            }}
            className={`px-frame px-focus flex items-center justify-center gap-2 py-3 text-lg transition-colors ${
              tab === t.id ? "px-glow" : "text-muted hover:text-ink"
            }`}
            style={{
              "--frame": tab === t.id ? t.color : "var(--color-night-600)",
              background: tab === t.id ? `color-mix(in srgb, ${t.color} 16%, var(--color-night-800))` : undefined,
            }}
          >
            <PixelIcon icon={t.icon} size={24} />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "meal" && !manualMeal ? (
        <MealLogger userId={userId} onLogged={onLogged} onManual={() => setManualMeal(true)} />
      ) : (
      <form onSubmit={submit} className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={tab === "sleep" ? "Night of" : "Date"} type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} required />

        {tab === "workout" && (
          <>
            <div>
              <span className="mb-1 block text-sm uppercase tracking-wider text-muted">Result</span>
              <div className="grid grid-cols-3 gap-2">
                {STATUSES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    aria-pressed={status === s.id}
                    onClick={() => setStatus(s.id)}
                    className={`px-frame px-focus py-2 text-lg ${status === s.id ? "bg-night-700 text-ink [--frame:var(--color-workouts)]" : "text-muted hover:text-ink"}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <Field label="Duration (optional)" type="number" inputMode="numeric" min={0} max={600} value={duration} onChange={(e) => setDuration(e.target.value)} suffix="min" placeholder="45" />
          </>
        )}

        {tab === "sleep" && (
          <Field label="Hours slept" type="number" inputMode="decimal" min={0} max={24} step={0.25} value={hours} onChange={(e) => setHours(e.target.value)} suffix="hrs" placeholder="7.5" required />
        )}

        {tab === "steps" && (
          <Field label="Steps" type="number" inputMode="numeric" min={0} max={200000} value={steps} onChange={(e) => setSteps(e.target.value)} suffix="steps" placeholder="8000" required />
        )}

        {tab === "meal" && (
          <>
            <label className="block">
              <span className="mb-1 block text-sm uppercase tracking-wider text-muted">Meal</span>
              <span className="px-frame flex bg-night-900/80 px-3 py-1 focus-within:[--frame:var(--color-cyan)]">
                <select value={meal.meal_type} onChange={setMealField("meal_type")} className="w-full cursor-pointer bg-transparent py-1 text-xl text-ink outline-none">
                  {MEAL_TYPES.map((m) => (
                    <option key={m} value={m} className="bg-night-900">
                      {m[0].toUpperCase() + m.slice(1)}
                    </option>
                  ))}
                </select>
              </span>
            </label>
            <Field label="Name (optional)" type="text" maxLength={120} value={meal.display_name} onChange={setMealField("display_name")} placeholder="Chicken rice bowl" />
            <Field label="Calories" type="number" inputMode="numeric" min={0} value={meal.calories} onChange={setMealField("calories")} suffix="kcal" placeholder="650" required />
            <Field label="Protein" type="number" inputMode="decimal" min={0} value={meal.protein_g} onChange={setMealField("protein_g")} suffix="g" placeholder="40" required />
            <Field label="Carbs" type="number" inputMode="decimal" min={0} value={meal.carbs_g} onChange={setMealField("carbs_g")} suffix="g" placeholder="70" required />
            <Field label="Fat" type="number" inputMode="decimal" min={0} value={meal.fat_g} onChange={setMealField("fat_g")} suffix="g" placeholder="20" required />
            <p className="text-sm text-muted sm:col-span-2 lg:col-span-3">
              Typing totals by hand.{" "}
              <button type="button" onClick={() => setManualMeal(false)} className="px-focus text-cyan hover:underline">
                Describe the meal instead
              </button>{" "}
              to have them looked up in the USDA food database. Nutrition needs meals on 3 different days before it gets a score.
            </p>
          </>
        )}

        <div className="flex flex-wrap items-center justify-end gap-4 sm:col-span-2 lg:col-span-3">
          {message && (
            <p role={message.ok ? "status" : "alert"} className={message.ok ? "text-activity" : "text-nutrition"}>
              {message.text}
            </p>
          )}
          <button
            type="submit"
            disabled={!valid || busy}
            className={`px-button px-6 py-3 text-lg ${!valid || busy ? "cursor-not-allowed bg-night-700 text-muted opacity-60" : "text-night-950"}`}
            style={
              !valid || busy
                ? { "--frame": "var(--color-night-500)", "--shadow": "var(--color-night-700)" }
                : { background: active.color, "--frame": "#ffffff", "--shadow": "var(--color-night-600)" }
            }
          >
            {busy ? "Saving..." : `Log ${active.label.toLowerCase()} ▶`}
          </button>
        </div>
      </form>
      )}
    </section>
  );
}

export default LogPanel;
