import { useRef } from "react";
import { demoDate, realToday, setDemoDate } from "../api";
import { clearQueryCache } from "../queryCache";

// Demo time travel: run the whole app as of another day (any date, future ones included). The plan,
// HealthScore, day log and logging all treat it as today. Switching reloads the page so every screen
// picks the new day up. `compact` is the corner button on the home page; otherwise it's the banner
// shown on every tab while a demo date is set.

function label(iso) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function travel(value) {
  setDemoDate(value);
  clearQueryCache();
  window.location.reload();
}

export function DemoDateButton() {
  const input = useRef(null);
  function open() {
    const el = input.current;
    if (!el) return;
    try {
      el.showPicker();
    } catch {
      el.focus();
      el.click();
    }
  }
  return (
    <span className="relative">
      <button type="button" onClick={open} title="Demo: run the app as of another day"
        className="px-focus border border-night-600 bg-night-900/85 px-2.5 py-1 text-muted transition-colors hover:border-cyan hover:text-cyan">
        📅 Jump to a date
      </button>
      <input ref={input} type="date" tabIndex={-1} aria-hidden="true" defaultValue={demoDate() ?? realToday()}
        onChange={(e) => e.target.value && travel(e.target.value)}
        className="pointer-events-none absolute inset-0 h-full w-full opacity-0 [color-scheme:dark]" />
    </span>
  );
}

// While a demo date is set: which day the app thinks it is, and the way back.
export function DemoDateBanner() {
  const day = demoDate();
  if (!day) return null;
  return (
    <div role="status" className="px-frame fixed bottom-4 right-4 z-30 flex items-center gap-3 bg-night-900/95 px-3 py-1.5 text-sm [--frame:var(--color-cyan)]">
      <span><span className="text-cyan">Demo date:</span> {label(day)}</span>
      <button type="button" onClick={() => travel(null)} className="px-focus text-muted hover:text-cyan">Back to today</button>
    </div>
  );
}
