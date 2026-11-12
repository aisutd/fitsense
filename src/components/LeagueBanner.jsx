import PixelAvatar from "./PixelAvatar";
import { fitnessLevel, leagueStyle } from "../game/leagues";

// The player's league banner: a face card of their avatar, league name and tier, season score,
// fitness level and place. The frame, pattern, glow and trim get fancier with every league.
const TITLE = { fontFamily: '"FitSense Title", "FitSense Pixel", monospace', fontWeight: 400 };

const MOVES = {
  "promotion zone": { label: "▲ Promotion zone", color: "#42e08b" },
  "demotion zone": { label: "▼ Demotion zone", color: "#ff6b81" },
  "holding position": { label: "◆ Holding", color: "#ffc61a" },
  "building a league": { label: "Building league", color: "#94a3c8" },
  "needs a HealthScore": { label: "Needs a HealthScore", color: "#94a3c8" },
};

function frameStyle(tier, L) {
  const premium = tier === 1 || tier === 3 || tier >= 5;
  const edge = [`0 -4px 0 0 ${L.color}`, `0 4px 0 0 ${L.color}`, `-4px 0 0 0 ${L.color}`, `4px 0 0 0 ${L.color}`];
  if (premium) edge.push(`inset 0 0 0 4px ${L.deep}`, `inset 0 0 0 6px ${L.light}`);
  edge.push(`0 0 ${18 + tier * 3}px -2px ${L.color}`);
  const alpha = ["14", "18", "1c", "20", "24", "28", "30", "34", "3a"][tier];
  return {
    background: [
      `repeating-linear-gradient(135deg, ${L.color}${alpha} 0 6px, transparent 6px 14px)`,
      `radial-gradient(120% 140% at 0% 0%, ${L.color}66 0%, transparent 55%)`,
      `radial-gradient(90% 120% at 100% 100%, ${L.deep}aa 0%, transparent 60%)`,
      L.bg,
    ].join(", "),
    boxShadow: edge.join(", "),
  };
}

const SPARKLES = [
  { top: 18, right: 24, s: 4 }, { top: 40, right: 64, s: 3 }, { top: 64, right: 18, s: 5 },
  { top: 26, right: 150, s: 3 }, { top: 150, right: 30, s: 4 }, { top: 96, right: 110, s: 3 },
];

function LeagueBanner({ league, player }) {
  const tier = Math.max(0, Math.min(8, Number(league?.tier) || 0));
  const L = leagueStyle(tier);
  const level = fitnessLevel(player?.fitness_level);
  const body = player?.avatar_body === "female" ? "female" : "male";
  const move = MOVES[league?.movement] || MOVES["holding position"];
  const score = league?.season_health_score;
  const sparkles = SPARKLES.slice(0, tier >= 6 ? 6 : tier >= 4 ? 3 : 0);
  const metal = `linear-gradient(160deg, ${L.light} 0%, ${L.color} 45%, ${L.deep} 100%)`;

  return (
    <section
      aria-label={`${L.name} league banner`}
      className="relative flex gap-4 p-4 pt-5 sm:gap-5 sm:pr-5"
      style={{ ...frameStyle(tier, L), color: "#fff", margin: 4 }}
    >
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1.5" style={{
        background: tier === 8 ? "linear-gradient(90deg, #4d6bff, #c77dff, #4fe3ff, #4d6bff)"
          : `linear-gradient(90deg, ${L.deep}, ${L.color}, ${L.light}, ${L.color}, ${L.deep})`,
      }} />
      {sparkles.map((s, i) => (
        <span key={i} aria-hidden="true" className="absolute" style={{
          top: s.top, right: s.right, width: s.s, height: s.s,
          background: i % 2 ? L.light : "#fff", boxShadow: `0 0 8px ${i % 2 ? L.light : "#fff"}`,
        }} />
      ))}
      {tier >= 4 && [["top-2.5 left-2"], ["top-2.5 right-2"], ["bottom-2 left-2"], ["bottom-2 right-2"]].map(([pos]) => (
        <span key={pos} aria-hidden="true" className={`absolute h-1.5 w-1.5 ${pos}`} style={{ background: L.light, boxShadow: `0 0 6px ${L.color}` }} />
      ))}

      {/* face card */}
      <div className="flex shrink-0 flex-col items-center gap-4">
        <div className="relative h-[104px] w-[104px]" style={{ boxShadow: `0 0 ${6 + tier}px ${L.color}` }}>
          <div className="absolute inset-0 flex items-end justify-center overflow-hidden"
               style={{ background: `radial-gradient(75% 65% at 50% 40%, ${L.color}99 0%, ${L.bg} 80%)` }}>
            <PixelAvatar tier={tier} level={player?.fitness_level} body={body} crop="bust" size={96} />
          </div>
          <div aria-hidden="true" className="absolute inset-0" style={{ boxShadow: `inset 0 0 0 3px ${L.color}, inset 0 0 0 5px ${L.deep}` }} />
          <span className="absolute -bottom-2.5 -left-2 flex h-[26px] min-w-8 items-center justify-center px-1.5 text-xl leading-none text-night-950"
                style={{ ...TITLE, background: metal, boxShadow: `0 0 0 2px ${L.deep}` }}>{L.numeral}</span>
        </div>
        <div aria-hidden="true" className="flex w-[84px] flex-wrap justify-center gap-[3px]">
          {Array.from({ length: 9 }, (_, i) => (
            <span key={i} className="h-1.5 w-1.5" style={{
              background: i <= tier ? L.light : "rgba(255,255,255,0.12)", boxShadow: i <= tier ? `0 0 6px ${L.color}` : "none",
            }} />
          ))}
        </div>
      </div>

      {/* details */}
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <span className="px-1.5 text-sm leading-5 tracking-[0.18em] text-night-950" style={{ background: L.light }}>LEAGUE</span>
          <span className="text-base tracking-wider" style={{ color: L.light }}>TIER {tier + 1}/9</span>
        </div>
        <h3 className="m-0 truncate text-4xl leading-[0.95]" style={{ ...TITLE, color: L.light, textShadow: `0 0 14px ${L.color}, 3px 3px 0 ${L.deep}` }}>{L.name}</h3>
        <p className="m-0 truncate text-xl leading-none">{player?.name || "You"}</p>
        <div className="mt-1 grid grid-cols-2 gap-2">
          <div className="px-2.5 py-1.5" style={{ background: "rgba(6,10,21,0.72)", boxShadow: `inset 0 0 0 2px ${L.color}` }}>
            <p className="m-0 text-sm tracking-wider" style={{ color: L.light }}>LEAGUE SCORE</p>
            <p className="m-0 text-3xl leading-none" style={{ ...TITLE, textShadow: `0 0 10px ${L.color}` }}>{score ?? "—"}</p>
          </div>
          <div className="px-2.5 py-1.5" style={{ background: "rgba(6,10,21,0.72)", boxShadow: `inset 0 0 0 2px ${level.color}` }}>
            <p className="m-0 text-sm tracking-wider" style={{ color: level.color }}>LEVEL</p>
            <p className="m-0 text-3xl leading-none" title={level.label} style={{ ...TITLE, textShadow: `0 0 10px ${level.color}` }}>
              {level.short}<span className="sr-only"> ({level.label})</span>
            </p>
          </div>
        </div>
        <div className="mt-0.5 flex flex-wrap items-center justify-between gap-2">
          <span className="text-lg">{league?.position ? `#${league.position} of ${league.members}` : "Unranked"}</span>
          <span className="px-2 text-base leading-[22px] text-night-950" style={{ background: move.color, boxShadow: `0 0 10px ${move.color}` }}>{move.label}</span>
        </div>
      </div>
    </section>
  );
}

export default LeagueBanner;
