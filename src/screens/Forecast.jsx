import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import DashboardHeader from "../components/DashboardHeader";
import WorkoutWhatIf from "../components/WorkoutWhatIf";
import { getForecasts } from "../api";

const SERIES = [
  { key: "weight_kg", title: "Body weight", unit: "lb", color: "#f7b733", convert: (n) => n * 2.20462262, digits: 1 },
  { key: "workouts_per_week", title: "Workouts", unit: "/ week", color: "#4d8dff", digits: 1 },
  { key: "daily_steps", title: "Daily steps", unit: "steps / day", color: "#42e08b", digits: 0 },
  { key: "health_score", title: "HealthScore", unit: "/ 100", color: "#a66bff", digits: 0 },
];
const HEALTH_CATEGORIES = ["workouts", "nutrition", "sleep", "activity"];
const HORIZONS = ["1 week", "4 weeks", "12 weeks"];

function number(value, digits = 1) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

function dateLabel(value, options = { month: "short", day: "numeric" }) {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

function modelLabel(version) {
  return version?.includes("xgb") ? "LINEAR + XGBOOST" : "LINEAR TREND";
}

const HORIZON_WEEKS = [1, 4, 12];
const HISTORY_WEEKS = 8;

// Width of an element in CSS pixels, so the chart is drawn 1:1 (text and dots keep their size).
function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(320);
  useEffect(() => {
    if (!ref.current) return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, Math.round(entry.contentRect.width))));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

// Past full weeks (solid) on the left, the forecast (dashed) with its 80% range (shaded) on the right.
// The right side isn't to scale: +1w, +4w and +12w are spaced evenly so all three stay readable.
function ForecastChart({ history, rows, color, title }) {
  const [ref, W] = useWidth();
  const H = 150, LEFT = 10, RIGHT = W - 18, TOP = 14, BOTTOM = 112;
  const past = history.slice(-HISTORY_WEEKS);
  const anchor = past.length ? past.at(-1) : null;
  const NOW = past.length ? LEFT + (RIGHT - LEFT) * 0.42 : LEFT;
  const pastX = (i) => (past.length === 1 ? NOW : LEFT + ((NOW - LEFT) * i) / (past.length - 1));
  const futureX = (i) => NOW + (RIGHT - NOW) * [0.3, 0.64, 1][i];
  const values = [...past.map((p) => p.value), ...rows.flatMap((r) => [r.predicted_value, r.low ?? r.predicted_value, r.high ?? r.predicted_value])];
  const min = Math.min(...values), max = Math.max(...values);
  const pad = (max - min) * 0.1 || Math.max(Math.abs(max) * 0.05, 1);
  const y = (v) => BOTTOM - ((v - (min - pad)) / (max - min + 2 * pad)) * (BOTTOM - TOP);

  const pastPts = past.map((p, i) => [pastX(i), y(p.value)]);
  const start = anchor ? [[NOW, y(anchor.value)]] : [];
  const futurePts = rows.map((r, i) => [futureX(i), y(r.predicted_value)]);
  const band = rows[0]?.low != null
    ? [...start, ...rows.map((r, i) => [futureX(i), y(r.high)]), ...rows.map((r, i) => [futureX(i), y(r.low)]).reverse()]
    : [];
  const line = (pts) => pts.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const label = { fill: "#94a3c8", fontSize: 12 };

  return (
    <div ref={ref} className="mt-4 w-full">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}: past weeks and forecast`} className="block overflow-visible">
        {[TOP, (TOP + BOTTOM) / 2, BOTTOM].map((gy) => <line key={gy} x1={LEFT} x2={RIGHT} y1={gy} y2={gy} stroke="#26345a" strokeDasharray="4 5" />)}
        {past.length > 0 && <line x1={NOW} x2={NOW} y1={TOP - 6} y2={BOTTOM + 4} stroke="#3b4a75" strokeWidth="2" />}
        {band.length > 0 && <polygon points={line(band)} fill={color} opacity="0.14" />}
        {pastPts.length > 1 && <polyline points={line(pastPts)} fill="none" stroke={color} strokeWidth="3" strokeLinejoin="round" />}
        <polyline points={line([...start, ...futurePts])} fill="none" stroke={color} strokeWidth="3" strokeDasharray="6 5" strokeLinejoin="round" />
        {pastPts.map(([px, py], i) => <circle key={`p${i}`} cx={px} cy={py} r="3.5" fill={color} />)}
        {futurePts.map(([px, py], i) => <circle key={`f${i}`} cx={px} cy={py} r="5.5" fill="#10192f" stroke={color} strokeWidth="3" />)}
        {past.length > 1 && <text x={LEFT} y={H - 8} {...label}>{past.length} wk ago</text>}
        {past.length > 0 && <text x={NOW} y={H - 8} textAnchor="middle" {...label}>now</text>}
        {futurePts.map(([px], i) => (
          <text key={`t${i}`} x={px} y={H - 8} textAnchor={i === futurePts.length - 1 ? "end" : "middle"} {...label}>+{HORIZON_WEEKS[i]}w</text>
        ))}
      </svg>
    </div>
  );
}

function MetricCard({ series, rows, history, note }) {
  const convert = (v) => (v == null ? v : series.convert ? series.convert(Number(v)) : Number(v));
  const converted = rows.map((row) => ({ ...row, predicted_value: convert(row.predicted_value), low: convert(row.low), high: convert(row.high) }));
  const past = (history ?? []).map((h) => ({ ...h, value: convert(h.value) }));
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="px-frame bg-night-800/90 p-5 sm:p-6"
      style={{ "--frame": series.color }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold" style={{ color: series.color }}>{series.title}</h2>
          <p className="mt-1 text-sm text-muted">
            {modelLabel(rows[0]?.model_version)} · {past.length ? `${past.length} full week${past.length === 1 ? "" : "s"} of data` : "no full weeks yet"}
          </p>
        </div>
        <span className="border border-night-600 px-2 py-1 text-sm text-muted">{series.unit}</span>
      </div>
      <ForecastChart history={past} rows={converted} color={series.color} title={series.title} />
      <div className="mt-2 grid grid-cols-3 gap-2 border-t border-night-700 pt-4">
        {converted.map((row, index) => (
          <div key={row.target_date}>
            <p className="text-sm text-muted">{HORIZONS[index]}</p>
            <p className="mt-1 text-xl font-bold">{number(row.predicted_value, series.digits)}</p>
            {row.low != null && (
              <p className="text-sm text-muted">{number(row.low, series.digits)}–{number(row.high, series.digits)}</p>
            )}
            <p className="text-sm text-muted">by {dateLabel(row.target_date)}</p>
          </div>
        ))}
      </div>
      {note && <p className="mt-3 text-sm text-gold">{note}</p>}
    </motion.section>
  );
}

function useForecasts(userId) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });
    getForecasts(userId)
      .then((data) => !cancelled && setState({ status: "ready", data, error: null }))
      .catch((error) => !cancelled && setState({ status: "error", data: null, error }));
    return () => { cancelled = true; };
  }, [userId, attempt]);

  return { ...state, retry: () => setAttempt((value) => value + 1) };
}

function Forecast({ userId, profile, onNavigate, onEditProfile, onLogout }) {
  const { status, data, error, retry } = useForecasts(userId);
  const groups = useMemo(() => {
    const map = new Map();
    for (const row of data?.forecasts ?? []) {
      if (!map.has(row.prediction_type)) map.set(row.prediction_type, []);
      map.get(row.prediction_type).push(row);
    }
    for (const rows of map.values()) rows.sort((a, b) => a.target_date.localeCompare(b.target_date));
    return map;
  }, [data]);
  const completeSeries = SERIES.filter((series) => groups.get(series.key)?.length === 3);
  const healthRows = HEALTH_CATEGORIES
    .map((category) => ({ category, rows: groups.get(`health_score_${category}`) }))
    .filter(({ rows }) => rows?.length === 3);

  return (
    <main className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-8 sm:pt-10">
      <DashboardHeader activeTab="forecast" onTabChange={onNavigate} onLogout={onLogout} />

      <div className="mt-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-cyan">Progress outlook</p>
          <h1 className="mt-2 text-5xl font-bold sm:text-6xl">Forecast</h1>
          <p className="mt-3 text-lg text-muted">Your projected progress{profile.name ? `, ${profile.name}` : ""}.</p>
        </div>
        {data?.generated_at && (
          <p className="px-frame bg-night-800/85 px-4 py-3 text-muted">
            Updated {dateLabel(data.generated_at, { month: "short", day: "numeric", year: "numeric" })}
          </p>
        )}
      </div>

      {status === "loading" && <p role="status" className="mt-10 text-lg text-muted">Loading forecast outputs…</p>}
      {status === "error" && (
        <div role="alert" className="px-frame mt-8 flex flex-wrap items-center justify-between gap-4 bg-night-800/85 px-5 py-4 [--frame:var(--color-nutrition)]">
          <p className="text-lg">{error.message}</p>
          <button type="button" onClick={retry} className="px-focus text-lg text-cyan hover:underline">Try again</button>
        </div>
      )}
      {status === "ready" && completeSeries.length === 0 && (
        <section className="px-frame mt-10 bg-night-800/90 p-6 sm:p-8 [--frame:var(--color-gold)]">
          <h2 className="text-2xl font-bold text-gold">No forecast outputs yet</h2>
          <p className="mt-3 max-w-2xl text-lg text-muted">
            Forecasts appear here after the weekly forecast job has generated results for your account.
            Body weight projections can start from your profile weight and become more personal as you log weigh-ins.
          </p>
          <button type="button" onClick={retry} className="px-focus mt-5 text-lg text-cyan hover:underline">Refresh forecasts ↻</button>
        </section>
      )}
      {status === "ready" && completeSeries.length > 0 && (
        <>
          <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
          <p className="text-muted">Fitted on your full weeks of logs · 1, 4 and 12 weeks ahead · shaded: the likely range (80%)</p>
          <button type="button" onClick={retry} className="px-focus text-lg text-cyan hover:underline">Recalculate ↻</button>
          </div>
          <div className="mt-5 grid gap-6 md:grid-cols-2">
            {completeSeries.map((series) => (
              <MetricCard key={series.key} series={series} rows={groups.get(series.key)} history={data.history?.[series.key]}
                note={series.key === "weight_kg" && data.notes?.weight_from_profile_only
                  ? `From your profile weight and goal, assuming you keep doing ${Math.round((data.notes.weight_adherence ?? 1) * 100)}% of your planned workouts. Log weigh-ins to make it yours.`
                  : null} />
            ))}
          </div>

          {data.workout_scenarios && <WorkoutWhatIf scenarios={data.workout_scenarios} />}

          {healthRows.length > 0 && (
            <section className="mt-12">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-3xl font-bold">HealthScore categories</h2>
                  <p className="mt-2 text-muted">Category-level projections used to calculate your overall score.</p>
                </div>
                <button type="button" onClick={onEditProfile} className="px-focus text-muted transition-colors hover:text-cyan">✎ Edit profile</button>
              </div>
              <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {healthRows.map(({ category, rows }) => (
                  <div key={category} className="px-frame bg-night-800/90 p-4" style={{ "--frame": "var(--color-sleep)" }}>
                    <p className="text-lg capitalize text-cyan">{category}</p>
                    <p className="mt-2 text-sm text-muted">At 1 / 4 / 12 weeks</p>
                    <p className="mt-1 text-xl font-bold">{rows.map((row) => number(Number(row.predicted_value), 0)).join(" · ")}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
          <p className="mt-10 text-center text-sm text-muted">
            Projections from your recent full weeks: a trend carries forward but levels off over time, and the range shows how much your weeks usually vary. Not guarantees. Weight is shown in pounds.
          </p>
        </>
      )}
    </main>
  );
}

export default Forecast;
