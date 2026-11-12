import { lazy, Suspense, useEffect, useState } from "react";
import { motion } from "motion/react";
import DashboardHeader from "../components/DashboardHeader";
import PixelIcon from "../components/PixelIcon";
import { ICONS } from "../icons";
import { getCurrentPlan, localToday, logWorkout, swapPlanDay, validationMessage } from "../api";
import { celebrate } from "../rewards";

// three.js and the body model load only when a plan day is shown
const MuscleMap = lazy(() => import("../components/MuscleMap"));

// This week's workout plan from the weekly plan model (weekly_plan.py): built from the profile in
// week 1, then adapted each week to how many plan days were completed. Logging a day here links the
// workout to that plan day, which is what next week's plan adapts to. Every week keeps at least one
// recovery day; the week strip shows which days are for training and which for recovery.

const BLUE = "#4d8dff";
const RECOVERY = "var(--color-sleep)";
const STATUS = {
  completed: { label: "Done", color: "var(--color-activity)" },
  partial: { label: "Partly done", color: "var(--color-gold)" },
  skipped: { label: "Skipped", color: "var(--color-nutrition)" },
};
const GROUP_COLOR = { "Upper Body": "#4d8dff", "Lower Body": "#42e08b", Core: "#f7b733", Cardio: "#ff5d6c", Mobility: "#a66bff", "Full Body": "#4fd8ff" };
const GOALS = { lose_weight: "Lose weight", build_muscle: "Build muscle", improve_endurance: "Endurance", general_fitness: "General fitness", increase_flexibility: "Flexibility" };

const shortDate = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const weekdayName = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" });

function usePlan(userId) {
  const [state, setState] = useState({ status: "loading", plan: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, status: "loading", error: null }));
    getCurrentPlan(userId)
      .then((plan) => !cancelled && setState({ status: "ready", plan, error: null }))
      .catch((error) => !cancelled && setState({ status: "error", plan: null, error }));
    return () => {
      cancelled = true;
    };
  }, [userId, attempt]);
  return { ...state, reload: () => setAttempt((n) => n + 1) };
}

// Equipment that can be "not here today" (bodyweight can't).
const SWAPPABLE = (equipment) => equipment && equipment !== "body only";
const equipmentLabel = (equipment) => (equipment === "other" ? "special equipment" : equipment);

function Exercise({ exercise, onSwap, busy }) {
  const [open, setOpen] = useState(false);
  const color = GROUP_COLOR[exercise.group] ?? BLUE;
  return (
    <li className="border-t-[3px] border-night-700 py-3 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-lg">{exercise.name}</p>
        <p className="text-lg text-cyan">{exercise.dose}</p>
      </div>
      <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
        <span className="px-frame px-1.5 uppercase tracking-wider" style={{ "--frame": color, color }}>{exercise.group}</span>
        <span>{exercise.level}</span>·<span>{exercise.equipment || "no equipment"}</span>
        {onSwap && (
          <button type="button" disabled={busy} onClick={() => onSwap({ exercises: [exercise.name] })}
                  className="px-focus ml-auto text-gold hover:underline disabled:opacity-50"
                  aria-label={`Swap ${exercise.name} for a similar exercise today`}>
            ⇄ Swap
          </button>
        )}
        {exercise.instructions?.length > 0 && (
          <button type="button" onClick={() => setOpen((o) => !o)} className={`px-focus text-cyan hover:underline ${onSwap ? "" : "ml-auto"}`} aria-expanded={open}>
            {open ? "Hide how-to" : "How to"}
          </button>
        )}
      </p>
      {open && (
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">
          {exercise.instructions.map((step, i) => <li key={i}>{step}</li>)}
        </ol>
      )}
    </li>
  );
}

function WeekStrip({ schedule, days, today, onSelect }) {
  const byDay = Object.fromEntries(days.map((d) => [d.day, d]));
  return (
    <ol className="mt-8 grid grid-cols-7 gap-1.5 sm:gap-3" aria-label="This week's training and recovery days">
      {schedule.map((entry) => {
        const status = entry.day ? STATUS[byDay[entry.day]?.status] : null;
        const color = entry.kind === "recovery" ? RECOVERY : status?.color ?? BLUE;
        const isToday = entry.date === today;
        const label = entry.kind === "recovery" ? "Recovery" : `Day ${entry.day}`;
        const inner = (
          <>
            <span className={`block text-sm ${isToday ? "text-cyan" : "text-muted"}`}>{isToday ? "Today" : entry.weekday}</span>
            <span className="block text-2xl sm:text-3xl" style={{ color }}>{entry.kind === "recovery" ? "R" : entry.day}</span>
            <span className="hidden text-sm sm:block" style={{ color }}>{status ? status.label : label}</span>
          </>
        );
        return (
          <li key={entry.date}>
            {entry.day ? (
              <a href={`#plan-day-${entry.day}`} onClick={(event) => { event.preventDefault(); onSelect(entry.day); }} aria-label={`${weekdayName(entry.date)}: ${label}${status ? `, ${status.label}` : ""}`}
                 aria-current={isToday ? "date" : undefined}
                 className="px-frame px-focus block bg-night-800/90 px-1 py-2 text-center hover:bg-night-700"
                 style={{ "--frame": isToday ? "var(--color-cyan)" : color }}>
                {inner}
              </a>
            ) : (
              <div aria-label={`${weekdayName(entry.date)}: recovery day`} aria-current={isToday ? "date" : undefined}
                   className="px-frame block bg-night-900/70 px-1 py-2 text-center"
                   style={{ "--frame": isToday ? "var(--color-cyan)" : "var(--color-night-600)" }}>
                {inner}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function RecoveryCard({ recovery, isToday }) {
  return (
    <section className="px-frame mt-6 bg-night-800/90 p-5 sm:p-6" style={{ "--frame": RECOVERY }} aria-labelledby="recovery-day">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="recovery-day" className="text-3xl" style={{ color: RECOVERY }}>
          {isToday ? "Today is a recovery day" : "Recovery days"}
        </h2>
        <p className="text-muted">Optional and light</p>
      </div>
      <p className="mt-3 text-lg text-muted">
        Rest lets your muscles rebuild, so the next workout goes better. Keep it easy: {recovery.walk}, and a few gentle stretches.
      </p>
      <ul className="mt-3">
        {recovery.exercises.map((exercise) => <Exercise key={exercise.name} exercise={exercise} />)}
      </ul>
    </section>
  );
}

// "Can't do it as planned today?": swap the day's exercises for what's available.
function SwapPanel({ day, busy, onSwap }) {
  const [open, setOpen] = useState(false);
  const missing = [...new Set(day.exercises.map((e) => e.equipment).filter(SWAPPABLE))];
  return (
    <div className="mt-4 border-t-[3px] border-night-700 pt-4">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="px-focus text-lg text-gold hover:underline">
        Can't do it as planned today? {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="mt-3">
          <p className="text-sm text-muted">
            Swaps today's exercises for similar ones you can do, keeping your sets and reps. Only this week changes.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {missing.map((equipment) => (
              <button key={equipment} type="button" disabled={busy} onClick={() => onSwap(day, { without: [equipment] })}
                      className="px-frame px-focus bg-night-900/80 px-3 py-1.5 text-lg text-ink hover:text-gold disabled:opacity-50 [--frame:var(--color-gold)]">
                No {equipmentLabel(equipment)} today
              </button>
            ))}
            {[["home", "Training at home"], ["outdoors", "Training outdoors"]].map(([location, label]) => (
              <button key={location} type="button" disabled={busy} onClick={() => onSwap(day, { location })}
                      className="px-frame px-focus bg-night-900/80 px-3 py-1.5 text-lg text-ink hover:text-gold disabled:opacity-50 [--frame:var(--color-gold)]">
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// aside: shown in a left column beside the day (today's muscle map); below it on narrow screens
function DayCard({ day, busy, onLog, onSwap, delay = 0, isToday = false, aside = null }) {
  const status = day.status ? STATUS[day.status] : null;
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 24, delay }}
      className="px-frame bg-night-800/90 p-5 sm:p-6"
      style={{ "--frame": status ? status.color : "var(--color-night-600)" }}
      aria-labelledby={`plan-day-title-${day.day}`}
    >
      <div className={aside ? "grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" : ""}>
        {aside && <div className="order-last lg:order-first lg:border-r-[3px] lg:border-night-700 lg:pr-8">{aside}</div>}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id={`plan-day-title-${day.day}`} className="text-3xl" style={{ color: BLUE }}>
              {isToday ? <><span className="text-cyan">Today</span> · Day {day.day}</> : `Day ${day.day}`}
            </h2>
            {status ? (
              <p style={{ color: status.color }}>
                {status.label}{day.logged_on ? ` · ${shortDate(day.logged_on)}` : ""}
              </p>
            ) : (
              <p className="text-muted">
                {day.scheduled_on ? `${weekdayName(day.scheduled_on)} · ` : ""}
                {day.exercises.length} exercise{day.exercises.length === 1 ? "" : "s"}
              </p>
            )}
          </div>
          <DayBody day={day} busy={busy} onLog={onLog} onSwap={onSwap} />
        </div>
      </div>
    </motion.section>
  );
}

// A plan day's exercises and its log buttons (inside today's card, or an opened row).
function DayBody({ day, busy, onLog, onSwap }) {
  const status = day.status ? STATUS[day.status] : null;   // swaps are offered only before a day is logged
  return (
    <>
      <ul className="mt-3">
        {day.exercises.map((exercise) => (
          <Exercise key={exercise.name} exercise={exercise} busy={busy}
                    onSwap={!status && onSwap ? (change) => onSwap(day, change) : null} />
        ))}
        {day.exercises.length === 0 && <li className="py-2 text-muted">No matching exercises for this day.</li>}
      </ul>
      {!status && onSwap && day.exercises.length > 0 && <SwapPanel day={day} busy={busy} onSwap={onSwap} />}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t-[3px] border-night-700 pt-4">
        <span className="mr-auto text-sm text-muted">{day.status ? "Change today's log:" : "Log it for today:"}</span>
        {["completed", "partial", "skipped"].map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            onClick={(event) => onLog(day, s, event.currentTarget)}
            aria-pressed={day.status === s}
            className="px-frame px-focus px-3 py-1.5 text-lg transition-colors hover:text-ink disabled:opacity-50"
            style={{ "--frame": STATUS[s].color, color: day.status === s ? "var(--color-night-950)" : STATUS[s].color,
                     background: day.status === s ? STATUS[s].color : undefined }}
          >
            {s === "completed" ? "Done ✓" : STATUS[s].label}
          </button>
        ))}
        {/* Skipping because the gym was closed or the equipment was missing doesn't count against next week. */}
        <button type="button" disabled={busy} onClick={(event) => onLog(day, "skipped", event.currentTarget, "no_equipment")}
                className="px-frame px-focus px-3 py-1.5 text-lg text-muted transition-colors hover:text-ink disabled:opacity-50"
                title="Doesn't count as a missed workout when next week's plan is made">
          Skipped: gym closed / no equipment
        </button>
      </div>
    </>
  );
}

// Another plan day, folded to one line: when it's planned or how it went. Opening it unfolds the
// exercises in the same box, e.g. to do a different day's workout today.
function DayRow({ day, open, onToggle, busy, onLog, onSwap }) {
  const status = day.status ? STATUS[day.status] : null;
  const when = status
    ? `${status.label}${day.logged_on ? ` · ${shortDate(day.logged_on)}` : ""}`
    : day.scheduled_on ? weekdayName(day.scheduled_on) : "Not scheduled";
  return (
    <li id={`plan-day-${day.day}`} className="px-frame scroll-mt-6 bg-night-800/90"
        style={{ "--frame": status ? status.color : "var(--color-night-600)" }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="px-focus flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-left text-lg hover:bg-night-700"
      >
        <span className="text-2xl" style={{ color: BLUE }}>Day {day.day}</span>
        <span style={{ color: status ? status.color : undefined }} className={status ? "" : "text-muted"}>{when}</span>
        <span className="ml-auto text-muted">
          {day.exercises.length} exercise{day.exercises.length === 1 ? "" : "s"} {open ? "▲" : "▼"}
        </span>
      </button>
      {open && (
        <div className="border-t-[3px] border-night-700 px-5 pb-5 sm:px-6">
          <DayBody day={day} busy={busy} onLog={onLog} onSwap={onSwap} />
        </div>
      )}
    </li>
  );
}

function WorkoutPlan({ userId, profile, onNavigate, onLogout, onEditProfile }) {
  const { status, plan, error, reload } = usePlan(userId);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const today = localToday();
  const restToday = plan?.schedule?.find((entry) => entry.date === today)?.kind === "recovery";
  // Only today's plan day is shown in full; the others fold into one-line rows.
  const todayNumber = plan?.schedule?.find((entry) => entry.date === today)?.day ?? null;
  const todayDay = plan?.days.find((day) => day.day === todayNumber);
  const otherDays = plan?.days.filter((day) => day.day !== todayNumber) ?? [];
  const [openDay, setOpenDay] = useState(null);
  function selectDay(number) {
    if (number !== todayNumber) setOpenDay(number);
    const target = number === todayNumber ? "plan-today" : `plan-day-${number}`;
    requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  // Plan days swapped this visit, so logging them tells next week's plan it was a swap, not a miss.
  const [swappedDays, setSwappedDays] = useState(() => new Set());

  async function log(day, completion, anchor, skipReason = null) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await logWorkout(userId, today, completion, null, {
        planId: plan.plan_id, dayNumber: day.day,
        swapped: completion !== "skipped" && swappedDays.has(day.day), skipReason,
      });
      celebrate(result, anchor);
      const reward = result?.rewards;
      const extras = [reward?.points_awarded && `+${reward.points_awarded} XP`, reward?.fitcoins_awarded && `+${reward.fitcoins_awarded} FitCoins`]
        .filter(Boolean).join(" ");
      const note = skipReason ? " It won't count against next week's plan." : "";
      setMessage({ ok: true, text: `Day ${day.day}: ${STATUS[completion].label.toLowerCase()}.${note}${extras ? ` ${extras}!` : ""}` });
      reload();
    } catch (err) {
      setMessage({ ok: false, text: validationMessage(err, "Couldn't save that. Please try again.") });
    } finally {
      setBusy(false);
    }
  }

  async function swap(day, change) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await swapPlanDay(userId, day.day, change);
      const done = result.swaps.filter((s) => s.to);
      const kept = result.swaps.filter((s) => !s.to);
      if (done.length) setSwappedDays((current) => new Set(current).add(day.day));
      setMessage({
        ok: done.length > 0,
        text: done.length
          ? `Swapped for today: ${done.map((s) => `${s.from} → ${s.to}`).join(", ")}.${kept.length ? ` No alternative for ${kept.map((s) => s.from).join(", ")}.` : ""}`
          : result.swaps.length ? `No alternative for ${kept.map((s) => s.from).join(", ")}, so it's unchanged.` : "Nothing needed swapping: everything on that day still works.",
      });
      reload();
    } catch (err) {
      setMessage({ ok: false, text: validationMessage(err, "Couldn't swap that. Please try again.") });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-8 sm:pt-10">
      <DashboardHeader activeTab="plan" onTabChange={onNavigate} onLogout={onLogout} />

      <div className="mt-10 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-cyan">This week</p>
          <h1 className="mt-2 text-5xl sm:text-6xl">Workout Plan</h1>
          <p className="mt-3 text-lg text-muted">
            {plan
              ? `${shortDate(plan.week_start)} – ${shortDate(plan.week_end)} · ${GOALS[plan.goal] ?? plan.goal} · ${plan.level}`
              : `Your plan for the week${profile.name ? `, ${profile.name}` : ""}.`}
          </p>
        </div>
        {plan && (
          <div className="px-frame flex items-center gap-3 bg-night-800/85 px-4 py-3">
            <PixelIcon icon={ICONS.dumbbell} size={28} />
            <p className="text-lg">
              <span className="text-2xl">{plan.done}</span>
              <span className="text-muted"> of {plan.days_per_week} day{plan.days_per_week === 1 ? "" : "s"} done</span>
            </p>
          </div>
        )}
      </div>

      {status === "loading" && !plan && <p role="status" className="mt-10 text-lg text-muted">Building your plan…</p>}
      {status === "error" && (
        <div role="alert" className="px-frame mt-8 flex flex-wrap items-center justify-between gap-4 bg-night-800/85 px-5 py-4 [--frame:var(--color-nutrition)]">
          <p className="text-lg">{error.message}</p>
          <button type="button" onClick={reload} className="px-focus text-lg text-cyan hover:underline">Try again</button>
        </div>
      )}

      {plan && (
        <>
          {plan.adaptation && (
            <p className="px-frame mt-8 bg-night-800/85 px-5 py-4 text-lg [--frame:var(--color-gold)]">
              <span className="text-gold">Adapted:</span> {plan.adaptation.text}{" "}
              <span className="text-muted">
                (last week {Math.round(plan.adaptation.last_week_completion * 100)}% done
                {plan.adaptation.last_week_completion_counted != null && plan.adaptation.last_week_completion_counted !== plan.adaptation.last_week_completion
                  ? `, ${Math.round(plan.adaptation.last_week_completion_counted * 100)}% of the days you could train`
                  : ""}
                {plan.days_per_week !== plan.planned_per_profile ? `; ${plan.days_per_week} of your ${plan.planned_per_profile} days this week` : ""}
                {plan.adaptation.decided_by === "xgboost"
                  ? `; chosen by the adaptation model${plan.adaptation.rule !== plan.adaptation.change ? `, the rule said ${plan.adaptation.rule}` : ""}`
                  : ""})
              </span>
            </p>
          )}
          {plan.schedule && <WeekStrip schedule={plan.schedule} days={plan.days} today={today} onSelect={selectDay} />}
          {plan.recovery && restToday && <RecoveryCard recovery={plan.recovery} isToday />}
          {message && (
            <p role={message.ok ? "status" : "alert"} className={`mt-6 text-lg ${message.ok ? "text-activity" : "text-nutrition"}`}>{message.text}</p>
          )}
          {todayDay && (
            <div id="plan-today" className="mt-8 scroll-mt-6">
              <DayCard
                day={todayDay}
                busy={busy}
                onLog={log}
                onSwap={swap}
                isToday
                aside={
                  <Suspense fallback={<p role="status" className="text-lg text-muted">Loading the muscle map…</p>}>
                    <MuscleMap exercises={todayDay.exercises} />
                  </Suspense>
                }
              />
            </div>
          )}
          {otherDays.length > 0 && (
            <section className="mt-10" aria-labelledby="plan-other-days">
              <h2 id="plan-other-days" className="text-2xl">{todayDay ? "Rest of the week" : "This week's plan days"}</h2>
              <ul className="mt-4 space-y-3">
                {otherDays.map((day) => (
                  <DayRow key={day.day} day={day} busy={busy} onLog={log} onSwap={swap} open={openDay === day.day}
                          onToggle={() => setOpenDay((current) => (current === day.day ? null : day.day))} />
                ))}
              </ul>
            </section>
          )}
          {plan.recovery && !restToday && <RecoveryCard recovery={plan.recovery} />}
          <p className="mt-10 text-center text-sm text-muted">
            Plans adapt every Monday: finish your plan days and the next week steps up; miss them and it gets lighter.
            A day skipped because the gym was closed or the equipment was missing doesn't count as missed, and you can swap exercises for the day when something's different.
            Every week keeps at least one recovery day; resting doesn't count against your HealthScore as long as the rest of the plan still fits in the week.
            Workouts logged on the HealthScore page count toward your next open plan day.{" "}
            <button type="button" onClick={onEditProfile} className="px-focus text-cyan hover:underline">Change goal or equipment</button>
          </p>
        </>
      )}
    </main>
  );
}

export default WorkoutPlan;
