// Sample player's weekly plans, how each week adapted, and the forecast after each week.
// Reads /sample_user.json, which `npm run dev` / `npm run build` regenerate first
// (package.json "sample-data" -> export_sample_user.py writes public/sample_user.json).
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";

// The theme's colours (index.css @theme), written out so they work in inline styles even when
// no Tailwind class uses them (Tailwind only emits the theme variables that classes use).
const DECISION_COLORS = {
  progress: "#42e08b",   // --color-activity
  "same dose": "#f7b733", // --color-gold
  reduce: "#ff5d6c",     // --color-nutrition
};
const WORKOUTS = "#4d8dff"; // --color-workouts

const rise = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.2 },
  transition: { type: "spring", stiffness: 200, damping: 22, delay },
});

function WorkoutsChart({ metric, plannedDays }) {
  // Logged weeks (solid) and the 1/4/12-week forecast (dashed), completed workouts per week.
  if (!metric) return null;
  const points = [
    ...metric.history.map((h) => ({ x: h.week, y: h.value, kind: "history" })),
    ...metric.predictions.map((p) => ({ x: p.date, y: p.value, kind: "forecast" })),
  ];
  const width = 420, height = 170, pad = 30;
  const times = points.map((p) => new Date(p.x).getTime());
  const t0 = Math.min(...times), t1 = Math.max(...times);
  const yMax = Math.max(plannedDays || 0, ...points.map((p) => p.y), 1);
  const sx = (x) => pad + ((new Date(x).getTime() - t0) / (t1 - t0 || 1)) * (width - 2 * pad);
  const sy = (y) => height - pad - (y / yMax) * (height - 2 * pad);
  const history = points.filter((p) => p.kind === "history");
  const forecast = [history[history.length - 1], ...points.filter((p) => p.kind === "forecast")].filter(Boolean);
  const line = (ps) => ps.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="my-3 block w-full max-w-xl" role="img"
         aria-label="Completed workouts per week: logged and forecast">
      <line x1={pad} x2={width - pad} y1={sy(0)} y2={sy(0)} stroke="var(--color-night-500)" strokeWidth="2" />
      {plannedDays ? (
        <g>
          <line x1={pad} x2={width - pad} y1={sy(plannedDays)} y2={sy(plannedDays)}
                stroke="var(--color-muted)" strokeDasharray="3 5" opacity="0.6" />
          <text x={width - pad} y={sy(plannedDays) - 6} fontSize="13" textAnchor="end" fill="var(--color-muted)">
            planned {plannedDays}/wk
          </text>
        </g>
      ) : null}
      <polyline points={line(history)} fill="none" stroke={WORKOUTS} strokeWidth="3" />
      <polyline points={line(forecast)} fill="none" stroke={WORKOUTS} strokeWidth="3" strokeDasharray="6 5" />
      {points.map((p, i) => (
        <rect key={i} x={sx(p.x) - 4} y={sy(p.y) - 4} width="8" height="8"
              fill={p.kind === "history" ? WORKOUTS : "var(--color-night-900)"} stroke={WORKOUTS} strokeWidth="2" />
      ))}
      <text x={pad} y={height - 8} fontSize="13" fill="var(--color-muted)">■ logged   □ forecast</text>
    </svg>
  );
}

function Plan({ plan }) {
  const days = [...new Set(plan.items.map((i) => i.day))];
  return (
    <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {days.map((day) => (
        <div key={day} className="px-frame bg-night-900/80 p-4">
          <p className="font-title text-lg font-bold text-cyan">Day {day}</p>
          <ul className="mt-2 space-y-3">
            {plan.items.filter((i) => i.day === day).map((i) => (
              <li key={i.group}>
                <p className="text-sm text-muted">{i.group}</p>
                <p className="text-lg leading-tight">{i.name}</p>
                <p className="text-workouts">{i.dose}</p>
                <p className="text-sm text-muted">{i.level} · {i.equipment}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, children, frame }) {
  return (
    <div className="px-frame mt-6 bg-night-900/80 p-5" style={frame ? { "--frame": frame } : undefined}>
      <h3 className="text-xl font-bold">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function adaptationNote(a) {
  if (!a) return "";
  const parts = [a.source === "xgboost" ? "Decided by the XGBoost adaptation model" : "Decided by the swap-aware rule"];
  if (a.source === "xgboost" && a.rule !== a.decision) parts.push(`rule said ${a.rule}`);
  if (a.original_rule !== a.rule) parts.push(`before swap-awareness it would have been ${a.original_rule}`);
  if (a.equipment_skips.length) parts.push(`equipment-blocked day ${a.equipment_skips.join(", ")} not counted as missed`);
  return parts.join("; ");
}

export default function SampleUserForecast({ src = "/sample_user.json" }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    fetch(src)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${src}: ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, [src]);

  const week = data?.weeks[index];
  // The latest forecast made on or before this week (the newest week has no logs yet).
  const forecastWeek = useMemo(
    () => data && [...data.weeks.slice(0, index + 1)].reverse().find((w) => w.forecast),
    [data, index]
  );

  let body;
  if (error) {
    body = <p className="mt-4 text-lg text-muted">Sample player not available ({error}). Run <code>npm run sample-data</code>.</p>;
  } else if (!data) {
    body = <p className="mt-4 text-lg text-muted">Loading sample player...</p>;
  } else {
    const user = week.profile;
    const fc = forecastWeek?.forecast;
    body = (
      <>
        <p className="mt-2 text-muted">
          Simulated weeks for {data.user.name}. Exercise order: {data.ranker_used ? "XGBoost ranker" : "rules"}.
          Week-to-week decision: {data.adaptation_model_used ? "XGBoost adaptation model within rule limits" : "swap-aware rule"}.
        </p>

        <div className="mt-5 flex flex-wrap gap-3" role="tablist" aria-label="Week">
          {data.weeks.map((w, i) => (
            <button key={w.week} type="button" role="tab" aria-selected={i === index} onClick={() => setIndex(i)}
                    className={`px-frame px-focus px-4 py-2 text-lg transition-colors ${
                      i === index ? "bg-night-600 text-cyan [--frame:var(--color-cyan)]" : "bg-night-900/80 text-muted hover:text-ink"}`}>
              Week {w.week}
            </button>
          ))}
        </div>

        <p className="mt-6 text-lg">
          <span className="text-cyan">Week of {week.plan.week_start}</span> · {week.plan.days} days · {user.fitness_level},{" "}
          {user.fitness_goal.replace("_", " ")}, {user.workout_location}, equipment:{" "}
          {user.equipment.length ? user.equipment.join(", ") : "none"}
        </p>
        <Plan plan={week.plan} />

        {week.changes.length > 0 && (
          <Panel title="What changed from last week">
            <ul className="space-y-1 text-muted">{week.changes.map((c) => <li key={c}>› {c}</li>)}</ul>
          </Panel>
        )}

        {week.ranker_effect.length > 0 && (
          <Panel title="Where the ranker picked differently">
            <ul className="space-y-1 text-muted">
              {week.ranker_effect.map((r) => (
                <li key={`${r.day}-${r.group}`}>› Day {r.day} {r.group}: rules → {r.rules_pick ?? "-"}, ranker → {r.ranker_pick ?? "-"}</li>
              ))}
            </ul>
          </Panel>
        )}

        {week.logged ? (
          <Panel title="What the player did" frame={DECISION_COLORS[week.decision]}>
            <p className="text-muted">{week.result_story}</p>
            <p className="mt-1 text-lg">
              {week.logged.map((l) => `Day ${l.day_number}: ${l.completion_status}`
                + (l.swapped ? " (swapped)" : "") + (l.skip_reason ? ` (${l.skip_reason.replace("_", " ")})` : "")).join(" · ")}
            </p>
            <p className="mt-2 text-xl">
              Completion {Math.round(week.completion * 100)}% →{" "}
              <span className="font-bold" style={{ color: DECISION_COLORS[week.decision] }}>{week.decision}</span>,{" "}
              {week.days_next} days next week
            </p>
            {week.adaptation && <p className="mt-1 text-sm text-muted">{adaptationNote(week.adaptation)}</p>}
            {Object.keys(week.profile_change).length > 0 && (
              <p className="mt-1 text-sm text-gold">
                Profile change: {Object.entries(week.profile_change).map(([k, v]) => `${k} → ${JSON.stringify(v)}`).join(", ")}
              </p>
            )}
          </Panel>
        ) : (
          <Panel title="What the player did"><p className="text-muted">This week hasn't been logged yet.</p></Panel>
        )}

        {fc && (
          <Panel title={`Forecast as of ${fc.as_of}`} frame={WORKOUTS}>
            <p className="text-sm text-muted">
              Linear regression on completed workouts{fc.weight_kg?.uses_xgboost ? "; weight corrected by XGBoost" : ""}.
            </p>
            <WorkoutsChart metric={fc.workouts_per_week} plannedDays={week.plan.days} />
            <div className="overflow-x-auto">
              <table className="text-lg">
                <thead>
                  <tr className="text-muted">
                    <th className="pr-6 text-left font-normal">Metric</th>
                    {fc.workouts_per_week.predictions.map((p) => (
                      <th key={p.weeks_ahead} className="pr-6 font-normal">{p.weeks_ahead} wk</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[["Workouts / week", fc.workouts_per_week], ["Weight (kg)", fc.weight_kg]].filter(([, m]) => m).map(([label, m]) => (
                    <tr key={label}>
                      <td className="pr-6">{label}</td>
                      {m.predictions.map((p) => <td key={p.weeks_ahead} className="pr-6 text-center">{p.value}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-sm text-muted">
              Based on {fc.workouts_per_week.weeks_of_data} week(s) of logs. Long-range numbers from a few weeks are rough.
            </p>
          </Panel>
        )}
      </>
    );
  }

  return (
    <motion.section {...rise(0)} className="px-frame mt-20 bg-night-800/85 p-6 sm:p-8">
      <h2 className="text-2xl font-bold">Sample Player: Workout Plan &amp; Forecast</h2>
      {body}
    </motion.section>
  );
}
