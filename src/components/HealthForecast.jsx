// HealthScore forecast for the logged-in player: where the score is heading, and how many
// workouts a week it takes to move it. Data: GET /forecast/{userId}/healthscore (backend/app/forecast.py).
import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";
import { getHealthForecast } from "../api";

// Theme colours (index.css @theme), written out for inline SVG styles.
const CYAN = "#4fd8ff";
const GOLD = "#f7b733";
const MUTED = "#94a3c8";
const GRID = "#3a4a78";

const rise = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.2 },
  transition: { type: "spring", stiffness: 200, damping: 22, delay },
});

const fmt = (v) => (v == null ? "--" : Math.round(v));
const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function ForecastChart({ history, trend, scenario }) {
  // Weekly HealthScore (solid), the current trend (dashed) and the chosen workouts-per-week path (gold).
  const width = 640, height = 220, padX = 36, padY = 22;
  const past = history.filter((h) => h.overall != null).map((h) => ({ x: h.week_start, y: h.overall }));
  // Forecast lines start from the latest real week, so they read as "from here".
  const start = past.length ? [past[past.length - 1]] : [];
  const trendLine = [...start, ...trend.predictions.map((p) => ({ x: p.date, y: p.value }))];
  const scenarioLine = scenario ? [...start, ...scenario.predictions.map((p) => ({ x: p.date, y: p.value }))] : [];
  const all = [...past, ...trendLine, ...scenarioLine];
  const times = all.map((p) => new Date(p.x).getTime());
  const t0 = Math.min(...times), t1 = Math.max(...times);
  const sx = (x) => padX + ((new Date(x).getTime() - t0) / (t1 - t0 || 1)) * (width - 2 * padX);
  const sy = (y) => height - padY - (y / 100) * (height - 2 * padY);
  const pts = (ps) => ps.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-4 block w-full" role="img"
         aria-label="HealthScore by week, with the forecast for the chosen number of workouts">
      {[0, 50, 100].map((v) => (
        <g key={v}>
          <line x1={padX} x2={width - padX} y1={sy(v)} y2={sy(v)} stroke={GRID} strokeWidth="1" strokeDasharray={v ? "2 6" : undefined} />
          <text x={padX - 8} y={sy(v) + 4} fontSize="13" textAnchor="end" fill={MUTED}>{v}</text>
        </g>
      ))}
      {past.length > 1 && <polyline points={pts(past)} fill="none" stroke={CYAN} strokeWidth="3" />}
      <polyline points={pts(trendLine)} fill="none" stroke={MUTED} strokeWidth="2" strokeDasharray="5 6" />
      {scenario && <polyline points={pts(scenarioLine)} fill="none" stroke={GOLD} strokeWidth="3" strokeDasharray="7 5" />}
      {past.map((p) => <rect key={p.x} x={sx(p.x) - 4} y={sy(p.y) - 4} width="8" height="8" fill={CYAN} />)}
      {scenario?.predictions.map((p) => (
        <rect key={p.date} x={sx(p.date) - 4} y={sy(p.value) - 4} width="8" height="8" fill="#0a1122" stroke={GOLD} strokeWidth="2" />
      ))}
      {trend.predictions.map((p) => (
        <text key={p.date} x={sx(p.date)} y={height - 4} fontSize="12" textAnchor="middle" fill={MUTED}>+{p.weeks_ahead} wk</text>
      ))}
    </svg>
  );
}

function Stat({ label, value, sub, color }) {
  return (
    <div className="px-frame bg-night-900/80 px-4 py-3">
      <p className="text-sm text-muted">{label}</p>
      <p className="text-4xl font-bold" style={color ? { color } : undefined}>{fmt(value)}</p>
      {sub && <p className="text-sm text-muted">{sub}</p>}
    </div>
  );
}

export default function HealthForecast({ userId, refreshToken }) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });
  const [chosen, setChosen] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getHealthForecast(userId)
      .then((data) => !cancelled && setState({ status: "ready", data, error: null }))
      .catch((error) => !cancelled && setState({ status: "error", data: null, error }));
    return () => {
      cancelled = true;
    };
  }, [userId, refreshToken]);

  const data = state.data;
  // Default choice: the player's current pace, rounded, else their plan.
  const defaultChoice = useMemo(() => {
    if (!data?.scenarios.length) return null;
    const pace = data.pace?.workouts_per_week;
    const target = pace != null ? Math.round(pace) : data.planned_workouts_per_week;
    return Math.min(target, data.scenarios[data.scenarios.length - 1].workouts_per_week);
  }, [data]);
  const selected = chosen ?? defaultChoice;
  const scenario = data?.scenarios.find((s) => s.workouts_per_week === selected);

  let body;
  if (state.status === "loading") {
    body = <p className="mt-4 text-lg text-muted">Loading forecast...</p>;
  } else if (state.status === "error") {
    body = <p className="mt-4 text-lg text-muted">Forecast unavailable: {state.error.message}</p>;
  } else if (data.based_on === "none") {
    body = (
      <p className="mt-4 text-lg text-muted">
        No forecast yet. Log a workout, a night's sleep, your steps or a meal and your HealthScore forecast appears here.
      </p>
    );
  } else {
    const t = data.trend;
    const scoredWeeks = data.history.filter((h) => h.overall != null);
    const latest = scoredWeeks.length ? scoredWeeks[scoredWeeks.length - 1].overall : t.now;
    const perWorkout = data.scenarios.length > 1
      ? data.scenarios[1].predictions[1].value - data.scenarios[0].predictions[1].value : null;
    const vsTrend = scenario ? scenario.predictions[1].value - t.predictions[1].value : null;
    body = (
      <>
        <p className="mt-2 text-muted">
          {data.based_on === "last_7_days"
            ? "Based on your last 7 days. It gets sharper after your first full week."
            : `Based on ${data.weeks_of_data} complete week${data.weeks_of_data === 1 ? "" : "s"} of logs.`}
          {data.missing.length > 0 && ` Not logged yet: ${data.missing.join(", ")}.`}
        </p>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Stat label={scoredWeeks.length ? "Last full week" : "Last 7 days"} value={latest} />
          <Stat label="In 4 weeks if the trend holds" value={t.predictions[1].value} />
          <Stat label="In 12 weeks if the trend holds" value={t.predictions[2].value} />
        </div>

        {data.scenarios.length > 0 && (
          <div className="px-frame mt-6 bg-night-900/80 p-5 [--frame:var(--color-gold)]">
            <div className="flex items-center gap-3">
              <PixelIcon icon={ICONS.dumbbell} size={28} />
              <h3 className="text-xl font-bold">What if you complete...</h3>
            </div>
            <div className="mt-4 flex flex-wrap gap-3" role="radiogroup" aria-label="Workouts per week">
              {data.scenarios.map((s) => (
                <button key={s.workouts_per_week} type="button" role="radio" aria-checked={s.workouts_per_week === selected}
                        onClick={() => setChosen(s.workouts_per_week)}
                        className={`px-frame px-focus min-w-14 px-3 py-2 text-lg transition-colors ${
                          s.workouts_per_week === selected ? "bg-night-600 text-gold [--frame:var(--color-gold)]" : "bg-night-800 text-muted hover:text-ink"}`}>
                  {s.workouts_per_week}
                </button>
              ))}
              <span className="self-center text-lg text-muted">workouts a week</span>
            </div>
            {scenario && (
              <div className="mt-5 grid gap-4 sm:grid-cols-3">
                <Stat label="Workouts score" value={scenario.workout_score} sub={`${selected} of ${data.scheduled_per_week} planned`} color={GOLD} />
                <Stat label="HealthScore in 4 weeks" value={scenario.predictions[1].value} color={GOLD}
                      sub={vsTrend == null ? null : `${vsTrend >= 0 ? "+" : ""}${Math.round(vsTrend)} vs your trend`} />
                <Stat label="HealthScore in 12 weeks" value={scenario.predictions[2].value} color={GOLD} />
              </div>
            )}
            <p className="mt-4 text-muted">
              {data.pace && `Your current pace: about ${data.pace.workouts_per_week} workouts a week. `}
              {perWorkout != null && perWorkout > 0 &&
                `Each extra workout a week is worth about +${Math.round(perWorkout)} HealthScore points, up to your ${data.planned_workouts_per_week}-day plan.`}
            </p>
          </div>
        )}

        <ForecastChart history={data.history} trend={t} scenario={scenario} />
        <p className="text-sm text-muted">
          <span style={{ color: CYAN }}>■</span> weekly HealthScore · <span style={{ color: MUTED }}>- -</span> trend ·{" "}
          <span style={{ color: GOLD }}>- -</span> {selected} workouts a week
          {data.history.length > 0 && ` · weeks from ${shortDate(data.history[0].week_start)}`}
        </p>
        <p className="mt-3 text-sm text-muted">{data.disclaimer}</p>
      </>
    );
  }

  return (
    <motion.section {...rise(0)} className="px-frame mt-20 bg-night-800/85 p-6 sm:p-8">
      <h2 className="text-2xl font-bold">HealthScore Forecast</h2>
      {body}
    </motion.section>
  );
}
