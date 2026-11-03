import { useEffect, useState } from "react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";
import { getDayLog } from "../api";
import { dayLabel, shiftDay } from "./DateSwitcher";

// What was logged on the day the HealthScore is showing.

const num = (n, digits = 0) => Number(n ?? 0).toLocaleString("en-US", { maximumFractionDigits: digits });
const STATUS_COLOR = { completed: "text-activity", partial: "text-gold", skipped: "text-nutrition" };

function Row({ icon, color, title, children }) {
  return (
    <div className="flex gap-4 border-t-[3px] border-night-700 py-4 first:border-t-0">
      <PixelIcon icon={icon} size={30} />
      <div className="min-w-0 flex-1">
        <p className="text-sm uppercase tracking-wider" style={{ color }}>{title}</p>
        <div className="mt-1 text-lg">{children}</div>
      </div>
    </div>
  );
}

function DayLog({ userId, date, today, refreshKey }) {
  const [state, setState] = useState({ status: "loading", day: null });

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
        <div className={`mt-4 ${status === "loading" ? "opacity-50" : ""}`}>
          <Row icon={ICONS.dumbbell} color="#4d8dff" title="Workouts">
            {day?.workouts?.length
              ? day.workouts.map((w) => (
                  <p key={w.workout_log_id}>
                    <span className={STATUS_COLOR[w.completion_status]}>{w.completion_status}</span>
                    {w.duration_minutes ? ` · ${w.duration_minutes} min` : ""}
                  </p>
                ))
              : empty}
          </Row>
          <Row icon={ICONS.moon} color="#a66bff" title={`Sleep, night of ${dayLabel(shiftDay(date, -1), today)}`}>
            {day?.sleep
              ? `${num(day.sleep.hours_slept, 2)} hours${day.sleep.sleep_quality ? ` · quality ${day.sleep.sleep_quality}/5` : ""}`
              : empty}
          </Row>
          <Row icon={ICONS.runner} color="#42e08b" title="Activity">
            {day?.activity
              ? [
                  day.activity.steps != null && `${num(day.activity.steps)} steps`,
                  day.activity.active_minutes != null && `${num(day.activity.active_minutes)} active min`,
                ].filter(Boolean).join(" · ") || empty
              : empty}
          </Row>
          <Row icon={ICONS.apple} color="#ff5d6c" title="Meals">
            {meals.length ? (
              <>
                <ul>
                  {meals.map((m) => (
                    <li key={m.meal_id} className="flex justify-between gap-4">
                      <span className="min-w-0 truncate">
                        {m.display_name || "Meal"}
                        {m.meal_type && <span className="text-muted"> · {m.meal_type}</span>}
                      </span>
                      <span className="shrink-0 text-muted">{num(m.calories)} kcal</span>
                    </li>
                  ))}
                </ul>
                {meals.length > 1 && (
                  <p className="mt-1 text-muted">Total {num(totals.calories)} kcal · {num(totals.protein, 1)} g protein</p>
                )}
              </>
            ) : empty}
          </Row>
        </div>
      )}
    </section>
  );
}

export default DayLog;
