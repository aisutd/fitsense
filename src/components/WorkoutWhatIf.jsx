// "What if you complete N workouts a week?" for the Forecast screen. Data: the workout_scenarios
// part of GET /forecasts/{userId} (backend/app/forecast_scenarios.py).
import { useState } from "react";

const GOLD = "#f7b733";
const round = (v) => (v == null ? "--" : Math.round(v));
const signed = (v) => `${v >= 0 ? "+" : ""}${Math.round(v)}`;

function Stat({ label, value, sub }) {
  return (
    <div className="px-frame bg-night-900/80 px-4 py-3">
      <p className="text-sm text-muted">{label}</p>
      <p className="text-4xl font-bold" style={{ color: GOLD }}>{round(value)}</p>
      {sub && <p className="text-sm text-muted">{sub}</p>}
    </div>
  );
}

export default function WorkoutWhatIf({ scenarios }) {
  const { options, pace, trend, planned_per_week: planned, scheduled_per_week: scheduled } = scenarios;
  const most = options[options.length - 1].workouts_per_week;
  const [chosen, setChosen] = useState(pace ? Math.min(Math.round(pace.workouts_per_week), most) : planned);
  const option = options.find((o) => o.workouts_per_week === chosen) ?? options[0];
  const perWorkout = options.length > 1 ? options[1].predictions[1].value - options[0].predictions[1].value : null;
  const vsTrend = option.predictions[1].value - trend[1].value;
  const best = Math.max(...options.map((o) => o.predictions[1].value));

  return (
    <section className="px-frame mt-12 bg-night-800/90 p-6 sm:p-8 [--frame:var(--color-gold)]">
      <h2 className="text-3xl font-bold">What if you complete...</h2>
      <p className="mt-2 text-muted">
        Your HealthScore if every week from now has this many workouts, with nutrition, sleep and activity following their forecasts.
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-3" role="radiogroup" aria-label="Workouts per week">
        {options.map((o) => (
          <button key={o.workouts_per_week} type="button" role="radio" aria-checked={o.workouts_per_week === chosen}
                  onClick={() => setChosen(o.workouts_per_week)}
                  className={`px-frame px-focus min-w-14 px-3 py-2 text-lg transition-colors ${
                    o.workouts_per_week === chosen ? "bg-night-600 text-gold [--frame:var(--color-gold)]" : "bg-night-900/80 text-muted hover:text-ink"}`}>
            {o.workouts_per_week}
          </button>
        ))}
        <span className="text-lg text-muted">workouts a week</span>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <Stat label="Workouts score" value={option.workout_score} sub={`${chosen} of ${scheduled} planned`} />
        <Stat label="HealthScore in 4 weeks" value={option.predictions[1].value} sub={`${signed(vsTrend)} vs your forecast`} />
        <Stat label="HealthScore in 12 weeks" value={option.predictions[2].value} />
      </div>

      {/* HealthScore in 4 weeks for every option, so the trade-off is visible at a glance */}
      <div className="mt-6 space-y-2" aria-hidden="true">
        {options.map((o) => (
          <div key={o.workouts_per_week} className="flex items-center gap-3">
            <span className="w-6 text-right text-muted">{o.workouts_per_week}</span>
            <div className="h-4 flex-1 bg-night-900/80">
              <div className="h-4" style={{ width: `${o.predictions[1].value}%`,
                background: o.workouts_per_week === chosen ? GOLD : "var(--color-night-500)" }} />
            </div>
            <span className={`w-10 text-right ${o.workouts_per_week === chosen ? "text-gold" : "text-muted"}`}>{round(o.predictions[1].value)}</span>
          </div>
        ))}
        <p className="text-sm text-muted">HealthScore in 4 weeks, by workouts a week</p>
      </div>

      <p className="mt-5 text-muted">
        {pace && `Your current pace: about ${pace.workouts_per_week} workouts a week. `}
        {perWorkout > 0 && `Each extra workout a week is worth about +${Math.round(perWorkout)} points, up to your ${planned}-day plan`}
        {perWorkout > 0 && (best > option.predictions[1].value ? ` (up to ${Math.round(best)} at ${planned} a week).` : ".")}
      </p>
    </section>
  );
}
