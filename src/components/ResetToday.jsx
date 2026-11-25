import { useState } from "react";
import { localToday, resetDay } from "../api";
import { DemoDateButton } from "./DemoDate";

// The home page's bottom left corner, for demos: a small button that undoes today's logging (workouts,
// steps, meals and last night's sleep; it asks first, then onReset() refreshes the page's data), and one
// that runs the app as of another day (DemoDate.jsx).
function ResetToday({ userId, onReset }) {
  const [step, setStep] = useState("idle");   // idle | confirm | busy
  const [note, setNote] = useState(null);

  async function reset() {
    setStep("busy");
    setNote(null);
    try {
      const { removed } = await resetDay(userId, localToday());
      const count = Object.values(removed).reduce((a, b) => a + b, 0);
      setNote({ ok: true, text: count ? "Today's logs are cleared." : "Nothing was logged today." });
      onReset?.();
    } catch (e) {
      setNote({ ok: false, text: `Couldn't reset today: ${e.message}` });
    } finally {
      setStep("idle");
      window.setTimeout(() => setNote(null), 4000);
    }
  }

  return (
    <div className="fixed bottom-4 left-4 z-30 flex flex-col items-start gap-2 text-sm">
      {note && (
        <p role={note.ok ? "status" : "alert"} className={`px-frame bg-night-900/95 px-3 py-1.5 ${note.ok ? "text-activity" : "text-nutrition"}`}>
          {note.text}
        </p>
      )}
      {step === "idle" ? (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setStep("confirm")} title="Clear everything logged today"
            className="px-focus border border-night-600 bg-night-900/85 px-2.5 py-1 text-muted transition-colors hover:border-nutrition hover:text-nutrition">
            ↺ Reset today
          </button>
          <DemoDateButton />
        </div>
      ) : (
        <div role="group" aria-label="Reset today's logs"
          className="px-frame flex items-center gap-2 bg-night-900/95 px-3 py-2 [--frame:var(--color-nutrition)]">
          <span>Clear today's workouts, steps, meals and last night's sleep?</span>
          <button type="button" disabled={step === "busy"} onClick={reset}
            className="px-focus border border-nutrition px-2 text-nutrition hover:bg-nutrition/15 disabled:opacity-50">
            {step === "busy" ? "Resetting…" : "Reset"}
          </button>
          <button type="button" disabled={step === "busy"} onClick={() => setStep("idle")} className="px-focus text-muted hover:text-ink">
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export default ResetToday;
