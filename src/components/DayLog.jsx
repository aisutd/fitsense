import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { usePopIn } from "../fx/popIn";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";
import { deleteMeal, getDayLog } from "../api";
import { dayLabel, shiftDay } from "./DateSwitcher";

// What was logged on the day the HealthScore is showing. A logged meal can be removed (it asks first);
// onChanged() then refreshes the score.

const num = (n, digits = 0) => Number(n ?? 0).toLocaleString("en-US", { maximumFractionDigits: digits });
const STATUS_COLOR = { completed: "text-activity", partial: "text-gold", skipped: "text-nutrition" };

function Row({ icon, color, title, pop, children }) {
  return (
    <motion.div {...pop} className="flex gap-4 border-t-[3px] border-night-700 py-4 first:border-t-0">
      <PixelIcon icon={icon} size={30} />
      <div className="min-w-0 flex-1">
        <p className="text-sm uppercase tracking-wider" style={{ color }}>{title}</p>
        <div className="mt-1 text-lg">{children}</div>
      </div>
    </motion.div>
  );
}

function DayLog({ userId, date, today, refreshKey, onChanged }) {
  const [state, setState] = useState({ status: "loading", day: null });
  const [confirming, setConfirming] = useState(null);   // meal_id waiting for "Remove?" to be confirmed
  const [removing, setRemoving] = useState(null);
  const [removeError, setRemoveError] = useState(null);

  async function removeMeal(meal) {
    setRemoving(meal.meal_id);
    setRemoveError(null);
    try {
      await deleteMeal(userId, meal.meal_id);
      // drop it straight away; the refresh confirms it
      setState((s) => ({ ...s, day: { ...s.day, meals: s.day.meals.filter((m) => m.meal_id !== meal.meal_id) } }));
      onChanged?.();
    } catch (e) {
      setRemoveError(`Couldn't remove ${meal.display_name || "that meal"}: ${e.message}`);
    } finally {
      setRemoving(null);
      setConfirming(null);
    }
  }
  const pop = usePopIn();   // the rows slide in one after another, like a React Bits AnimatedList

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, status: "loading" }));
    getDayLog(userId, date)
      .then((day) => !cancelled && setState({ status: "ready", day }))
      .catch(() => !cancelled && setState({ status: "error", day: null }));
    return () => {
      cancelled = true;
    };
  }, [userId, date, refreshKey]);

  const { status, day } = state;
  const relative = date === today || date === shiftDay(today, -1);   // "Today" / "Yesterday" get the date too
  const heading = relative
    ? `${dayLabel(date, today)}, ${new Date(`${date}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}`
    : dayLabel(date, today);
  const empty = <span className="text-muted">Nothing logged.</span>;
  const meals = day?.meals ?? [];
  const totals = meals.reduce((t, m) => ({ calories: t.calories + Number(m.calories ?? 0), protein: t.protein + Number(m.protein_g ?? 0) }),
    { calories: 0, protein: 0 });

  return (
    <section className="px-frame mt-14 bg-night-800/85 p-6 sm:p-8" aria-labelledby="day-log-title">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="day-log-title" className="text-2xl font-bold">{heading}</h2>
        <p className="text-muted">{date === today ? "Day in progress: steps and meals still count." : "What you logged that day."}</p>
      </div>

      {status === "error" && <p className="mt-4 text-nutrition">Couldn't load this day.</p>}
      {status !== "error" && (
        <motion.div {...pop.list} className={`mt-4 ${status === "loading" ? "opacity-50" : ""}`}>
          <Row pop={pop.item} icon={ICONS.dumbbell} color="#4d8dff" title="Workouts">
            {day?.workouts?.length
              ? day.workouts.map((w) => (
                  <p key={w.workout_log_id}>
                    <span className={STATUS_COLOR[w.completion_status]}>{w.completion_status}</span>
                    {w.duration_minutes ? ` · ${w.duration_minutes} min` : ""}
                  </p>
                ))
              : empty}
          </Row>
          <Row pop={pop.item} icon={ICONS.moon} color="#a66bff" title={`Sleep, night of ${dayLabel(shiftDay(date, -1), today)}`}>
            {day?.sleep
              ? `${num(day.sleep.hours_slept, 2)} hours${day.sleep.sleep_quality ? ` · quality ${day.sleep.sleep_quality}/5` : ""}`
              : empty}
          </Row>
          <Row pop={pop.item} icon={ICONS.runner} color="#42e08b" title="Activity">
            {day?.activity
              ? [
                  day.activity.steps != null && `${num(day.activity.steps)} steps`,
                  day.activity.active_minutes != null && `${num(day.activity.active_minutes)} active min`,
                ].filter(Boolean).join(" · ") || empty
              : empty}
          </Row>
          <Row pop={pop.item} icon={ICONS.apple} color="#ff5d6c" title="Meals">
            {meals.length ? (
              <>
                <ul>
                  {meals.map((m) => (
                    <li key={m.meal_id} className="flex items-center justify-between gap-4">
                      <span className="min-w-0 truncate">
                        {m.display_name || "Meal"}
                        {m.meal_type && <span className="text-muted"> · {m.meal_type}</span>}
                      </span>
                      <span className="flex shrink-0 items-center gap-3">
                        <span className="text-muted">{num(m.calories)} kcal</span>
                        {confirming === m.meal_id ? (
                          <span className="flex items-center gap-2 text-sm">
                            <button type="button" disabled={removing === m.meal_id} onClick={() => removeMeal(m)}
                              className="px-focus border border-nutrition px-2 text-nutrition hover:bg-nutrition/15 disabled:opacity-50">
                              {removing === m.meal_id ? "Removing…" : "Remove"}
                            </button>
                            <button type="button" disabled={removing === m.meal_id} onClick={() => setConfirming(null)}
                              className="px-focus text-muted hover:text-ink">Keep</button>
                          </span>
                        ) : (
                          <button type="button" onClick={() => setConfirming(m.meal_id)}
                            aria-label={`Remove ${m.display_name || "meal"}`} title="Remove this meal"
                            className="px-focus px-1 text-muted hover:text-nutrition">✕</button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
                {removeError && <p role="alert" className="mt-1 text-sm text-nutrition">{removeError}</p>}
                {meals.length > 1 && (
                  <p className="mt-1 text-muted">Total {num(totals.calories)} kcal · {num(totals.protein, 1)} g protein</p>
                )}
              </>
            ) : empty}
          </Row>
        </motion.div>
      )}
    </section>
  );
}

export default DayLog;
