import { useEffect, useState } from "react";
import { queries } from "../queries";
import { peekQuery, refetch } from "../queryCache";
import { announcerMode, RARITY, rewardLine, setAnnouncerMode } from "../achievements";

// The System's achievements on the League tab, one category at a time. Earned ones show their title and
// dry one-liner; hovering (or focusing / tapping) one brings up the System's commentary. Visible goals are
// dimmed, hidden ones are "???" with a hint. Refreshes when a new one is announced. Snarky / Plain decides
// what the announcements (and these cards) say.

const TITLE = { fontFamily: '"FitSense Title", "FitSense Pixel", monospace', fontWeight: 400 };
const CATEGORIES = [
  { key: "activity", label: "Steps", match: ["activity"] },
  { key: "sleep", label: "Sleep", match: ["sleep"] },
  { key: "nutrition", label: "Food", match: ["nutrition"] },
  { key: "workout", label: "Workouts", match: ["workout"] },
  { key: "consistency", label: "Streaks & scores", match: ["consistency"] },
  { key: "league", label: "League & shop", match: ["league", "shop"] },
];

function earnedOn(value) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Card({ item, mode }) {
  const rarity = RARITY[item.rarity] ?? RARITY.common;
  if (!item.earned) {
    return (
      <li className="border-2 border-dashed border-night-600 bg-night-900/40 p-4">
        <div className="flex items-center justify-between gap-2 text-xs uppercase tracking-widest">
          <span style={{ color: `${rarity.color}aa` }}>{rarity.label}</span>
          <span className="text-muted" aria-hidden="true">{item.hidden ? "🔒" : "○"}</span>
        </div>
        <h3 className="mt-2 text-xl text-muted" style={TITLE}>{item.name}</h3>
        <p className="mt-1 text-sm italic text-muted">{item.hidden ? item.hint : item.plain}</p>
      </li>
    );
  }
  const snarky = mode !== "plain";
  return (
    <li
      tabIndex={snarky ? 0 : undefined}
      aria-describedby={snarky ? `quip-${item.code}` : undefined}
      className="group relative px-frame bg-night-900/70 p-4 outline-none focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-cyan"
      style={{ "--frame": rarity.color }}
    >
      <div className="flex items-center justify-between gap-2 text-xs uppercase tracking-widest">
        <span style={{ color: rarity.color }}>{rarity.label}</span>
        <span className="text-muted">{earnedOn(item.earned_at)}</span>
      </div>
      <h3 className="mt-2 text-xl" style={{ ...TITLE, color: rarity.color }}>{item.name}</h3>
      <p className={`mt-1 text-sm ${snarky ? "italic text-muted" : ""}`}>{snarky ? item.description : item.plain}</p>
      {snarky ? (
        // the System's quip, shown over the card on hover / focus
        <div
          id={`quip-${item.code}`}
          role="tooltip"
          className="pointer-events-none absolute inset-x-0 top-0 z-20 min-h-full bg-night-950/95 p-4 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100"
          style={{ boxShadow: `inset 0 0 0 3px ${rarity.color}, 0 0 22px ${rarity.color}55` }}
        >
          <p className="text-xs tracking-[0.2em] text-cyan">▣ THE SYSTEM</p>
          <p className="mt-2 text-sm leading-snug">{item.commentary}</p>
          <p className="mt-2 text-xs text-gold">{rewardLine(item)}</p>
        </div>
      ) : (
        <p className="mt-2 text-xs text-gold">{rewardLine(item)}</p>
      )}
    </li>
  );
}

function AchievementList({ userId }) {
  const [data, setData] = useState(() => peekQuery(queries.achievements(userId)) ?? null);
  const [error, setError] = useState(null);
  const [category, setCategory] = useState(CATEGORIES[0].key);
  const [mode, setMode] = useState(announcerMode);

  useEffect(() => {
    let cancelled = false;
    // first load can share a prefetch; after an announcement, ask again
    const load = (share) => refetch(queries.achievements(userId), { shareInFlight: share === true })
      .then((result) => { if (!cancelled) { setData(result); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e.message); });
    load(true);
    window.addEventListener("fitsense:achievements", load);
    return () => { cancelled = true; window.removeEventListener("fitsense:achievements", load); };
  }, [userId]);

  function chooseMode(next) {
    setMode(next);
    setAnnouncerMode(next);
  }

  const inCategory = (c) => (data?.items ?? []).filter((i) => c.match.includes(i.category));
  const current = CATEGORIES.find((c) => c.key === category);
  const items = inCategory(current);
  return (
    <section className="px-frame mt-10 bg-night-800/90 p-5 sm:p-7 [--frame:var(--color-cyan)]" aria-labelledby="achievements-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-cyan">▣ The System</p>
          <h2 id="achievements-title" className="mt-1 text-3xl">Achievements</h2>
          <p className="mt-1 text-sm text-muted">
            Out-of-the-ordinary things you do. Most stay secret until you do them.{mode !== "plain" && " Hover one to hear from the System."}
          </p>
        </div>
        {data && <p className="text-4xl">{data.earned}<span className="text-lg text-muted">/{data.total} earned</span></p>}
      </div>

      {data && (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
          {Object.entries(data.by_rarity).map(([key, count]) => (
            <span key={key} style={{ color: RARITY[key]?.color }}>
              {RARITY[key]?.label} {count.earned}/{count.total}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t-[3px] border-night-700 pt-4 text-sm">
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Achievement categories">
          {CATEGORIES.map((c) => {
            const all = inCategory(c);
            const selected = c.key === category;
            return (
              <button key={c.key} type="button" role="tab" aria-selected={selected} aria-controls="achievement-cards"
                onClick={() => setCategory(c.key)}
                className={`px-focus border px-3 py-1 ${selected ? "border-cyan bg-cyan/10 text-cyan" : "border-night-600 text-muted hover:border-cyan"}`}>
                {c.label}
                {data && <span className={selected ? "ml-1.5 text-cyan/70" : "ml-1.5 text-muted/70"}>{all.filter((i) => i.earned).length}/{all.length}</span>}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2" role="group" aria-label="Announcer">
          <span className="text-muted">Announcer:</span>
          {[["snarky", "Snarky"], ["plain", "Plain"]].map(([key, label]) => (
            <button key={key} type="button" aria-pressed={mode === key} onClick={() => chooseMode(key)}
              className={`px-focus border px-3 py-1 ${mode === key ? "border-cyan bg-cyan/10 text-cyan" : "border-night-600 text-muted hover:border-cyan"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && <p role="alert" className="mt-4 text-nutrition">{error}</p>}
      {!data && !error && <p role="status" className="mt-4 text-muted">The System is consulting its records…</p>}
      {data && (
        <ul id="achievement-cards" role="tabpanel" aria-label={current.label} className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => <Card key={item.code} item={item} mode={mode} />)}
        </ul>
      )}
    </section>
  );
}

export default AchievementList;
