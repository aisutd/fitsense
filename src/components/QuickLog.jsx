import { useEffect, useRef, useState } from "react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";
import { dayLabel, shiftDay } from "./DateSwitcher";
import { analyzeMeal, confirmMeal, discardMeal, logActivity, logSleep, logWorkout, validationMessage } from "../api";
import { celebrate } from "../rewards";

// The small pop-up a HealthScore ring section opens: log that category for the day on screen in a tap
// or two. Meals are described in words and looked up like in the full meal logger, which is one click
// away for anything that needs adjusting.

const SETUP = {
  workouts: { title: "Log a workout", icon: ICONS.dumbbell, color: "var(--color-workouts)" },
  sleep: { title: "Log sleep", icon: ICONS.moon, color: "var(--color-sleep)" },
  activity: { title: "Log steps", icon: ICONS.runner, color: "var(--color-activity)" },
  nutrition: { title: "Log a meal", icon: ICONS.apple, color: "var(--color-nutrition)" },
};
// Where the pop-up opens: centered over the ring on phones, beside its section from sm up.
const PLACE = {
  workouts: "top-[6%] sm:left-[56%]",
  sleep: "top-[50%] sm:left-[56%]",
  activity: "top-[50%] sm:right-[56%] sm:left-auto",
  nutrition: "top-[6%] sm:right-[56%] sm:left-auto",
};
const WORKOUT_RESULTS = [
  { id: "completed", label: "Done ✓", color: "var(--color-activity)" },
  { id: "partial", label: "Partly", color: "var(--color-gold)" },
  { id: "skipped", label: "Skipped", color: "var(--color-nutrition)" },
];
const SLEEP_CHIPS = [6, 7, 8, 9];
const STEP_CHIPS = [4000, 8000, 12000];

const chip = "px-frame px-focus px-3 py-2 text-lg transition-colors hover:text-ink disabled:opacity-50";

function NumberLog({ label, suffix, min, max, step, chips, format, busy, color, onLog }) {
  const [value, setValue] = useState("");
  const number = value === "" ? NaN : Number(value);
  const valid = number >= min && number <= max && (step !== 1 || Number.isInteger(number));
  return (
    <>
      <div className="mt-4 flex flex-wrap gap-2">
        {chips.map((c) => (
          <button key={c} type="button" disabled={busy} onClick={(e) => onLog(c, e.currentTarget)} className={chip}
                  style={{ "--frame": color }}>
            {format(c)}
          </button>
        ))}
      </div>
      <form className="mt-3 flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (valid) onLog(number, e.nativeEvent.submitter); }}>
        <label className="min-w-0 flex-1">
          <span className="mb-1 block text-sm uppercase tracking-wider text-muted">{label}</span>
          <span className="px-frame flex items-center gap-2 bg-night-900/80 px-3 py-1 focus-within:[--frame:var(--color-cyan)]">
            <input type="number" inputMode="decimal" min={min} max={max} step={step} value={value}
                   onChange={(e) => setValue(e.target.value)} className="w-full min-w-0 bg-transparent py-1 text-xl text-ink outline-none" />
            <span className="shrink-0 text-muted">{suffix}</span>
          </span>
        </label>
        <button type="submit" disabled={!valid || busy} className={`${chip} text-night-950`}
                style={{ "--frame": "#ffffff", background: valid && !busy ? color : "var(--color-night-700)" }}>
          Log
        </button>
      </form>
    </>
  );
}

function MealLog({ userId, date, busy, setBusy, setError, onSave, onOpenMealLogger }) {
  const [text, setText] = useState("");
  const [meal, setMeal] = useState(null);
  const unmatched = meal?.items.filter((item) => !item.food) ?? [];

  async function lookUp(event) {
    event.preventDefault();
    if (text.trim().length < 2 || busy) return;
    setBusy(true);
    setError(null);
    try {
      setMeal(await analyzeMeal(userId, text.trim(), date, null));
    } catch (err) {
      setError(validationMessage(err, "Couldn't look that up. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    const open = meal;
    setMeal(null);
    if (open) await discardMeal(open.meal_id).catch(() => {});
  }

  if (!meal) {
    return (
      <form className="mt-4" onSubmit={lookUp}>
        <label className="block">
          <span className="mb-1 block text-sm uppercase tracking-wider text-muted">What did you eat?</span>
          <span className="px-frame flex bg-night-900/80 px-3 py-1 focus-within:[--frame:var(--color-cyan)]">
            <input type="text" value={text} maxLength={300} onChange={(e) => setText(e.target.value)} placeholder="2 eggs and toast"
                   className="w-full min-w-0 bg-transparent py-1 text-xl text-ink outline-none" />
          </span>
        </label>
        <div className="mt-3 flex items-center justify-between gap-3">
          <button type="button" onClick={onOpenMealLogger} className="px-focus text-sm text-cyan hover:underline">Full meal logger</button>
          <button type="submit" disabled={busy || text.trim().length < 2} className={`${chip} text-night-950`}
                  style={{ "--frame": "#ffffff", background: text.trim().length >= 2 && !busy ? "var(--color-nutrition)" : "var(--color-night-700)" }}>
            {busy ? "Looking up…" : "Look it up"}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="mt-4">
      <ul className="max-h-40 overflow-y-auto">
        {meal.items.map((item) => (
          <li key={item.meal_item_id} className="flex justify-between gap-3 border-t-2 border-night-700 py-1.5 first:border-t-0">
            <span className="min-w-0">
              {item.ingredient_text}
              <span className={`block truncate text-sm ${item.food ? "text-muted" : "text-nutrition"}`}>
                {item.food ? item.food.description : "No match: pick it in the meal logger"}
              </span>
            </span>
            <span className="shrink-0">{Math.round(item.calories ?? 0)} kcal</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-lg">
        Total <span className="text-nutrition">{Math.round(meal.totals?.calories ?? 0)} kcal</span>
        <span className="text-sm text-muted"> · {Math.round(meal.totals?.protein_g ?? 0)} g protein</span>
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-end gap-3">
        <button type="button" disabled={busy} onClick={discard} className="px-focus text-muted hover:text-nutrition">Discard</button>
        <button type="button" onClick={onOpenMealLogger} className="px-focus text-cyan hover:underline">Adjust</button>
        <button type="button" disabled={busy || unmatched.length > 0 || meal.items.length === 0}
                onClick={(e) => onSave(() => confirmMeal(meal.meal_id), e.currentTarget)}
                className={`${chip} text-night-950`}
                style={{ "--frame": "#ffffff", background: unmatched.length || busy ? "var(--color-night-700)" : "var(--color-activity)" }}>
          Log meal
        </button>
      </div>
    </div>
  );
}

function QuickLog({ category, userId, date, today, anchor, onClose, onLogged, onOpenMealLogger }) {
  const setup = SETUP[category];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const panel = useRef(null);
  const when = date === today ? "today" : dayLabel(date, today);

  useEffect(() => {
    panel.current?.querySelector("input, button:not([data-close])")?.focus();
  }, [category]);

  useEffect(() => {
    const close = (refocus) => {
      onClose();
      if (refocus) anchor?.focus();
    };
    const onKey = (e) => e.key === "Escape" && close(true);
    // a click on another ring section switches the pop-up instead (the section handles that)
    const onDown = (e) => !panel.current?.contains(e.target) && !e.target.closest?.("[data-quadrant]") && close(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [onClose, anchor]);

  async function save(action, button) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      celebrate(result, button);
      onLogged();
      onClose();
    } catch (err) {
      setError(validationMessage(err, "Couldn't save that. Please try again."));
      setBusy(false);
    }
  }

  return (
    <div
      ref={panel}
      role="dialog"
      aria-label={`${setup.title} for ${when}`}
      className={`px-frame absolute left-1/2 z-30 w-[min(20rem,calc(100vw-2rem))] -translate-x-1/2 bg-night-800/95 p-4 shadow-2xl sm:translate-x-0 ${PLACE[category]}`}
      style={{ "--frame": setup.color }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <PixelIcon icon={setup.icon} size={26} />
          <div>
            <h2 className="text-2xl leading-none" style={{ color: setup.color }}>{setup.title}</h2>
            <p className="text-sm text-muted">
              {category === "sleep" ? (when === "today" ? "Last night" : `Night before ${when}`) : `For ${when}`}
            </p>
          </div>
        </div>
        <button type="button" data-close onClick={() => { onClose(); anchor?.focus(); }} aria-label="Close"
                className="px-focus text-2xl leading-none text-muted hover:text-ink">×</button>
      </div>

      {category === "workouts" && (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {WORKOUT_RESULTS.map((r) => (
            <button key={r.id} type="button" disabled={busy} className={chip} style={{ "--frame": r.color, color: r.color }}
                    onClick={(e) => save(() => logWorkout(userId, date, r.id, null), e.currentTarget)}>
              {r.label}
            </button>
          ))}
        </div>
      )}
      {category === "sleep" && (
        <NumberLog label="Hours slept" suffix="hrs" min={0} max={24} step={0.25} chips={SLEEP_CHIPS} format={(h) => `${h} h`}
                   busy={busy} color={setup.color}
                   onLog={(hours, button) => save(() => logSleep(userId, shiftDay(date, -1), hours), button)} />
      )}
      {category === "activity" && (
        <NumberLog label="Steps" suffix="steps" min={0} max={200000} step={1} chips={STEP_CHIPS} format={(s) => s.toLocaleString("en-US")}
                   busy={busy} color={setup.color}
                   onLog={(steps, button) => save(() => logActivity(userId, date, steps), button)} />
      )}
      {category === "nutrition" && (
        <MealLog userId={userId} date={date} busy={busy} setBusy={setBusy} setError={setError} onSave={save}
                 onOpenMealLogger={() => { onClose(); onOpenMealLogger(); }} />
      )}

      {error && <p role="alert" className="mt-3 text-nutrition">{error}</p>}
    </div>
  );
}

export default QuickLog;
