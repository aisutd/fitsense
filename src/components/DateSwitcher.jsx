import { useRef } from "react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";

// Pick the day the HealthScore shows: previous / next day, or a calendar for any past date.

export function shiftDay(iso, days) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function dayLabel(iso, today) {
  if (iso === today) return "Today";
  if (iso === shiftDay(today, -1)) return "Yesterday";
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function DateSwitcher({ value, today, min, onChange }) {
  const picker = useRef(null);
  const atToday = value >= today;
  const atStart = min && value <= min;

  function openCalendar() {
    const input = picker.current;
    if (!input) return;
    if (typeof input.showPicker === "function") {
      try {
        input.showPicker();
        return;
      } catch {
        // some browsers only allow showPicker from certain gestures; fall back to focusing
      }
    }
    input.focus();
    input.click();
  }

  const arrow = "px-focus flex h-11 w-11 items-center justify-center text-xl disabled:cursor-not-allowed disabled:opacity-30";
  return (
    <div className="px-frame flex items-center bg-night-800/85" role="group" aria-label="Day shown">
      <button type="button" className={`${arrow} hover:text-cyan`} onClick={() => onChange(shiftDay(value, -1))}
        disabled={atStart} aria-label="Previous day">
        ◀
      </button>
      <button type="button" onClick={openCalendar} aria-label={`Choose a day (showing ${dayLabel(value, today)})`}
        className="px-focus relative flex min-w-44 items-center justify-center gap-3 border-x-[3px] border-night-700 px-4 py-2 text-lg hover:text-cyan">
        <PixelIcon icon={ICONS.calendar} size={22} />
        <span>{dayLabel(value, today)}</span>
        {/* Invisible native date input: gives every browser a real calendar */}
        <input
          ref={picker}
          type="date"
          value={value}
          max={today}
          min={min}
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => e.target.value && onChange(e.target.value > today ? today : e.target.value)}
          className="pointer-events-none absolute inset-0 h-full w-full opacity-0 [color-scheme:dark]"
        />
      </button>
      <button type="button" className={`${arrow} hover:text-cyan`} onClick={() => onChange(shiftDay(value, 1))}
        disabled={atToday} aria-label="Next day">
        ▶
      </button>
    </div>
  );
}

export default DateSwitcher;
