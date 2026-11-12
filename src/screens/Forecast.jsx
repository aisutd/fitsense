import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import DashboardHeader from "../components/DashboardHeader";
import WorkoutWhatIf from "../components/WorkoutWhatIf";
import PixelCard from "../components/reactbits/PixelCard";
import PixelIcon from "../components/PixelIcon";
import ScoreRing from "../components/ScoreRing";
import { ICONS } from "../icons";
import { getForecasts, getGoals } from "../api";

// The four forecasts, laid out like the HealthScore page: a card each around a ring. A card (or its
// ring section) opens the full forecast, with its chart, below.
const SERIES = [
  { key: "weight_kg", title: "Body weight", label: "Body weight", short: "Weight", unit: "lb", color: "#f7b733",
    shades: ["#fff1c4", "#ffd27a", "#f7b733"], icon: ICONS.kettlebell, convert: (n) => n * 2.20462262, digits: 1 },
  { key: "workouts_per_week", title: "Workouts", label: "Workouts", short: "Workouts", unit: "/ week", color: "#4d8dff",
    shades: ["#d6e4ff", "#8fb6ff", "#4d8dff"], icon: ICONS.dumbbell, digits: 1 },
  { key: "daily_steps", title: "Daily steps", label: "Daily steps", short: "Steps", unit: "steps / day", color: "#42e08b",
    shades: ["#d1ffe6", "#86f0b6", "#42e08b"], icon: ICONS.runner, digits: 0 },
  { key: "health_score", title: "HealthScore", label: "HealthScore", short: "HealthScore", unit: "/ 100", color: "#a66bff",
    shades: ["#eadbff", "#c7a2ff", "#a66bff"], icon: ICONS.trophy, digits: 0 },
];
// Ring quadrants clockwise from 12 o'clock, matching the cards: the right column top and bottom, then the left.
const RING_ORDER = ["workouts_per_week", "health_score", "daily_steps", "weight_kg"];
const LEFT = ["weight_kg", "daily_steps"];
const RIGHT = ["workouts_per_week", "health_score"];
// A steady weekly change in pounds that fills the weight ring, for goals that aim to change weight.
const WEIGHT_PACE = { "Lose Weight": -0.5, "Build Muscle": 0.25 };
const DEFAULT_STEPS = 8000;

const HEALTH_CATEGORIES = ["workouts", "nutrition", "sleep", "activity"];
const HORIZONS = ["1 week", "4 weeks", "12 weeks"];
const HORIZON_SHORT = ["1 wk", "4 wks", "12 wks"];

function number(value, digits = 1) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

function dateLabel(value, options = { month: "short", day: "numeric" }) {
  if (!value) return "—";
  // a plain date is a calendar day; a timestamp (generated_at) is shown on the local calendar
  const date = new Date(value.length > 10 ? value : `${value}T12:00:00`);
  return new Intl.DateTimeFormat(undefined, options).format(date);
}

// The change from the latest full week, e.g. "▼ 2.4 from now", or "steady" when it rounds to nothing.
function changeLabel(change, digits) {
  const shown = number(Math.abs(change), digits);
  if (Number(shown.replace(/[^0-9.]/g, "")) === 0) return "steady";
  return `${change > 0 ? "▲ +" : "▼ "}${shown} from now`;
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

// A series in display units (pounds for weight): its forecast rows and past full weeks.
function inUnits(series, rows, history) {
  const convert = (v) => (v == null ? v : series.convert ? series.convert(Number(v)) : Number(v));
  return {
    rows: rows.map((row) => ({ ...row, predicted_value: convert(row.predicted_value), low: convert(row.low), high: convert(row.high) })),
    past: (history ?? []).map((h) => ({ ...h, value: convert(h.value) })),
  };
}

// How full a series' ring section is at a horizon (0-100), and what that measures.
function ringFill(series, value, now, weeks, profile, stepsTarget) {
  const share = (x) => Math.round(Math.min(1, Math.max(0, x)) * 100);
  if (series.key === "health_score") return { score: share(value / 100), meaning: "Ring: the projected score" };
  if (series.key === "workouts_per_week") {
    const planned = Number(profile.workoutDays) || 3;
    return { score: share(value / planned), meaning: `Ring: share of your ${planned} / week plan` };
  }
  if (series.key === "daily_steps") {
    return { score: share(value / stepsTarget), meaning: `Ring: share of your ${number(stepsTarget, 0)}-step goal` };
  }
  const pace = WEIGHT_PACE[profile.goal];
  if (now == null) return { score: 0, meaning: "Ring: pace for your goal" };
  const change = value - now;
  if (pace) return { score: share(change / (pace * weeks)), meaning: `Ring: pace toward "${profile.goal}"` };
  return { score: share(1 - Math.abs(change) / (0.5 * weeks)), meaning: "Ring: how steady your weight stays" };
}

// One forecast, collapsed to its value at the chosen horizon. The whole card opens the full forecast.
function SeriesCard({ series, view, horizon, side, delay, open, onToggle }) {
  return (
    <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 22, delay }} className="relative">
      <PixelCard className="hs-card px-frame px-glow" style={{ "--frame": series.color }} colors={series.shades}
        glowColor={series.color} gap={7} speed={30} radius={0} introDelay={delay * 1000 + 300} tabIndex={-1}>
        <button type="button" aria-label={`${open ? "Close" : "Open"} the ${series.title.toLowerCase()} forecast`}
          aria-expanded={open} aria-controls="forecast-detail" onClick={onToggle}
          className="inset-0 cursor-pointer outline-none focus-visible:outline-[3px] focus-visible:outline-offset-4 focus-visible:outline-cyan"
          style={{ position: "absolute", zIndex: 10 }} // inline: PixelCard makes its children position: relative
        />
        <div className="w-full p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <PixelIcon icon={series.icon} size={36} />
            <h3 className="text-2xl font-bold" style={{ color: series.color }}>{series.short}</h3>
          </div>
          <motion.p key={horizon} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-3 text-4xl font-bold">
            {number(view.value, series.digits)}
            <span className="ml-2 text-xl text-muted">{series.unit}</span>
          </motion.p>
          <p className="mt-2 text-muted">
            in {HORIZONS[horizon]}
            {view.change != null && ` · ${changeLabel(view.change, series.digits)}`}
          </p>
          {/* the badge sits bottom right: the titles are too long to share a line with it */}
          <div className="mt-2 flex items-end justify-between gap-3">
            <p className="text-sm text-muted">{view.meaning}</p>
            <span aria-hidden="true" className="shrink-0 whitespace-nowrap border-2 px-2 text-lg leading-tight"
              style={{ borderColor: series.color, color: open ? "var(--color-night-950)" : series.color,
                       background: open ? series.color : undefined }}>
              {open ? "× Close" : "+ Open"}
            </span>
          </div>
        </div>
      </PixelCard>

      {/* Connector to the ring (desktop layout only) */}
      <div aria-hidden="true"
        className={`absolute top-1/2 hidden h-[3px] w-12 lg:block ${side === "left" ? "-right-14" : "-left-14"}`}
        style={{ background: series.color, boxShadow: `0 0 10px ${series.color}` }}>
        <span className={`absolute -top-[5px] h-[13px] w-[13px] border-[3px] bg-night-900 ${side === "left" ? "-right-2" : "-left-2"}`}
          style={{ borderColor: series.color }} />
      </div>
    </motion.div>
  );
}

// The opened forecast: the chart of past weeks and the forecast, and every horizon (children: extras).
function MetricCard({ series, rows: apiRows, history, note, onClose, children }) {
  const { rows, past } = inUnits(series, apiRows, history);
  return (
    <section id="forecast-detail" className="px-frame bg-night-800/90 p-5 sm:p-6" style={{ "--frame": series.color }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <PixelIcon icon={series.icon} size={36} />
          <div>
            <h2 className="text-2xl font-bold" style={{ color: series.color }}>{series.title}</h2>
            <p className="mt-1 text-sm text-muted">
              {modelLabel(apiRows[0]?.model_version)} · {past.length ? `${past.length} full week${past.length === 1 ? "" : "s"} of data` : "no full weeks yet"} · {series.unit}
            </p>
          </div>
        </div>
        <button type="button" onClick={onClose} className="px-focus border-2 px-2 text-lg leading-tight"
          style={{ borderColor: series.color, color: series.color }}>
          × Close
        </button>
      </div>
      <ForecastChart history={past} rows={rows} color={series.color} title={series.title} />
      <div className="mt-2 grid grid-cols-3 gap-2 border-t border-night-700 pt-4">
        {rows.map((row, index) => (
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
      {children}
    </section>
  );
}

function HorizonPicker({ value, onChange }) {
  return (
    <div className="px-frame flex bg-night-800/85" role="radiogroup" aria-label="How far ahead">
      {HORIZON_SHORT.map((label, i) => (
        <button key={label} type="button" role="radio" aria-checked={value === i} onClick={() => onChange(i)}
          className={`px-focus px-4 py-2 text-lg ${i > 0 ? "border-l-[3px] border-night-700" : ""} ${
            value === i ? "bg-cyan text-night-950" : "hover:text-cyan"}`}>
          {label}
        </button>
      ))}
    </div>
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

// The steps goal the HealthScore uses (the ring shows the forecast against it).
function useStepsTarget(userId) {
  const [target, setTarget] = useState(DEFAULT_STEPS);
  useEffect(() => {
    let cancelled = false;
    getGoals(userId).then((goals) => !cancelled && goals?.daily_steps && setTarget(goals.daily_steps)).catch(() => {});
    return () => { cancelled = true; };
  }, [userId]);
  return target;
}

function Forecast({ userId, profile, onNavigate, onEditProfile, onLogout }) {
  const { status, data, error, retry } = useForecasts(userId);
  const stepsTarget = useStepsTarget(userId);
  const [horizon, setHorizon] = useState(1); // 4 weeks
  const [openKey, setOpenKey] = useState(null);
  const detail = useRef(null);
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

  // each series at the chosen horizon: value, change from the latest full week, and its ring section
  const views = Object.fromEntries(completeSeries.map((series) => {
    const { rows, past } = inUnits(series, groups.get(series.key), data?.history?.[series.key]);
    const value = rows[horizon].predicted_value;
    const now = past.length ? past.at(-1).value : series.key === "weight_kg" && profile.weight ? Number(profile.weight) : null;
    const fill = ringFill(series, value, now, HORIZON_WEEKS[horizon], profile, stepsTarget);
    return [series.key, { value, change: now == null ? null : value - now, ...fill }];
  }));

  // a series without a forecast yet leaves its ring section dark
  const ringScores = Object.fromEntries(SERIES.map((s) => [s.key, { score: views[s.key]?.score ?? 0 }]));
  const opened = completeSeries.find((s) => s.key === openKey);
  const toggle = (key) => setOpenKey((current) => (current === key ? null : key));

  useEffect(() => {
    if (openKey) detail.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [openKey]);

  const card = (key, side, delay) => {
    const series = completeSeries.find((s) => s.key === key);
    return series && (
      <SeriesCard key={key} series={series} view={views[key]} horizon={horizon} side={side} delay={delay}
        open={openKey === key} onToggle={() => toggle(key)} />
    );
  };

  return (
    <main className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-8 sm:pt-10">
      <DashboardHeader activeTab="forecast" onTabChange={onNavigate} onLogout={onLogout} />

      <div className="mt-10 flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-cyan">Progress outlook</p>
          <h1 className="mt-2 text-5xl font-bold sm:text-6xl">Forecast</h1>
          <p className="mt-3 text-lg text-muted">Your projected progress{profile.name ? `, ${profile.name}` : ""}.</p>
        </div>
        {status === "ready" && completeSeries.length > 0 && <HorizonPicker value={horizon} onChange={setHorizon} />}
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
            <p className="text-muted">
              Fitted on your full weeks of logs{data?.generated_at ? ` · updated ${dateLabel(data.generated_at)}` : ""} · open a card for its chart
            </p>
            <button type="button" onClick={retry} className="px-focus text-lg text-cyan hover:underline">Recalculate ↻</button>
          </div>

          {data?.workout_scenarios && <WorkoutWhatIf scenarios={data.workout_scenarios} />}

          <div className="mt-12 grid items-center gap-8 lg:grid-cols-[1fr_minmax(300px,420px)_1fr] lg:gap-x-16 lg:gap-y-0">
            <div className="grid gap-8 sm:grid-cols-2 lg:order-1 lg:grid-cols-1 lg:gap-24">
              {LEFT.map((key, i) => card(key, "left", 0.35 + i * 0.2))}
            </div>

            <motion.div
              className="relative order-first mx-auto w-full max-w-[420px] lg:order-2"
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: "spring", stiffness: 160, damping: 18, delay: 0.15 }}
            >
              <ScoreRing
                key={horizon}
                scores={ringScores}
                categories={SERIES}
                order={RING_ORDER}
                action="Open"
                picked={openKey}
                onPick={(key) => setOpenKey(key)}
              >
                <div className="flex flex-col items-center text-center">
                  <PixelIcon icon={ICONS.hourglass} size={48} className="h-auto w-8 drop-shadow-[0_0_12px_#4fd8ff80] sm:w-12" />
                  <p className="mt-1 text-5xl font-bold leading-none sm:mt-2 sm:text-7xl">{HORIZON_WEEKS[horizon]}</p>
                  <p className="text-base text-muted sm:text-xl">{horizon === 0 ? "week" : "weeks"} ahead</p>
                  <p className="text-base sm:mt-1 sm:text-xl">Forecast</p>
                </div>
              </ScoreRing>
              <p className="mt-3 text-center text-sm text-muted">Tap a section of the ring or a card to open it.</p>
            </motion.div>

            <div className="grid gap-8 sm:grid-cols-2 lg:order-3 lg:grid-cols-1 lg:gap-24">
              {RIGHT.map((key, i) => card(key, "right", 0.45 + i * 0.2))}
            </div>
          </div>

          <div ref={detail} className="mt-14 scroll-mt-6">
            <AnimatePresence mode="wait">
              {opened && (
                <motion.div key={opened.key} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 12 }} transition={{ duration: 0.25 }}>
                  <MetricCard series={opened} rows={groups.get(opened.key)} history={data.history?.[opened.key]}
                    onClose={() => setOpenKey(null)}
                    note={opened.key === "weight_kg" && data.notes?.weight_from_profile_only
                      ? `From your profile weight and goal, assuming you keep doing ${Math.round((data.notes.weight_adherence ?? 1) * 100)}% of your planned workouts. Log weigh-ins to make it yours.`
                      : null}>
                    {opened.key === "health_score" && healthRows.length > 0 && (
                      <div className="mt-6 border-t border-night-700 pt-5">
                        <div className="flex flex-wrap items-end justify-between gap-3">
                          <div>
                            <h3 className="text-xl font-bold">By category</h3>
                            <p className="mt-1 text-sm text-muted">The category projections behind the overall score.</p>
                          </div>
                          <button type="button" onClick={onEditProfile} className="px-focus text-muted transition-colors hover:text-cyan">✎ Edit profile</button>
                        </div>
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                          {healthRows.map(({ category, rows }) => (
                            <div key={category} className="px-frame bg-night-900/70 p-4" style={{ "--frame": "var(--color-sleep)" }}>
                              <p className="text-lg capitalize text-cyan">{category}</p>
                              <p className="mt-2 text-sm text-muted">At 1 / 4 / 12 weeks</p>
                              <p className="mt-1 text-xl font-bold">{rows.map((row) => number(Number(row.predicted_value), 0)).join(" · ")}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </MetricCard>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <p className="mt-10 text-center text-sm text-muted">
            Projections from your recent full weeks: a trend carries forward but levels off over time, and the range shows how much your weeks usually vary. Not guarantees. Weight is shown in pounds.
          </p>
        </>
      )}
    </main>
  );
}

export default Forecast;
