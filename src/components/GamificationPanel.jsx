import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import PixelIcon from "./PixelIcon";
import { equipAvatar, getAvatarInventory, getGamification, getLeague, purchaseAvatar } from "../api";

// The League tab: the season leaderboard front and center, then streaks, badges and the avatar shop,
// and the ladder of league ranks at the bottom.

const EMPTY = { league: null, inventory: null, status: null };
const STREAK_LABELS = { checkin: "Daily check-in", workout: "Workout days in a row", daily_goals: "Daily goals", sleep: "Sleep" };
// Each league rank's color, lowest to highest
const RANK_COLORS = {
  Bronze: "#cd7f32", "Bronze Premium": "#e39b5a", Silver: "#aeb8cc", "Silver Premium": "#dfe7f5", Gold: "#f7b733",
  Platinum: "#6fe3d0", Ruby: "#ff4d6d", Diamond: "#7cc8ff", Sapphire: "#4a6cff",
};
const MEDALS = { 1: "#f7b733", 2: "#c9d2e3", 3: "#cd7f32" };
const ZONES = {
  promotion: { color: "var(--color-activity)", label: "▲ Up" },
  demotion: { color: "var(--color-nutrition)", label: "▼ Down" },
};

function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  return `#${[n >> 16, (n >> 8) & 255, n & 255]
    .map((c) => Math.round(amount > 0 ? c + (255 - c) * amount : c * (1 + amount)))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
}

// A pixel gem in a rank's color, lit from the top left like the app's other icons
const GEM_ART = ["..hhhhh..", ".hllllmm.", "hllllmmmd", "dmmmmmmmd", ".dmmmmmd.", "..dmmmd..", "...dmd...", "....d...."];
function RankGem({ name, size = 28 }) {
  const color = RANK_COLORS[name] ?? "#4fd8ff";
  return <PixelIcon icon={{ art: GEM_ART, colors: { h: shade(color, 0.7), l: shade(color, 0.35), m: color, d: shade(color, -0.45) } }} size={size} />;
}

function FitCoin({ amount, animate = false }) {
  return (
    <motion.span
      key={`${amount}-${animate ? "reward" : "still"}`}
      initial={animate ? { scale: 0.6, rotate: -25 } : false}
      animate={{ scale: 1, rotate: 0 }}
      transition={{ type: "spring", stiffness: 420, damping: 16 }}
      className="inline-flex items-center gap-2 font-bold text-gold"
    >
      <span aria-hidden="true" className="inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-gold bg-[#473416] text-lg shadow-[0_0_16px_#f7b73355]">F</span>
      <span>{amount.toLocaleString()}</span>
      <span className="text-sm tracking-wide">FITCOINS</span>
    </motion.span>
  );
}

function movementText(movement) {
  return {
    "promotion zone": "You're on track to move up a rank.",
    "demotion zone": "Keep your momentum to hold your rank.",
    "building a league": "More players are needed before this league can move.",
    "needs a HealthScore": "Log some activity to enter this season's standings.",
  }[movement] ?? "You're holding your rank.";
}

function Leaderboard({ league, avatars }) {
  const { league: rank, season, standings } = league;
  const color = RANK_COLORS[rank.name] ?? "#4fd8ff";
  const listRef = useRef(null);
  const emoji = (id) => avatars.find((a) => a.id === id)?.emoji || "🧑‍🚀";

  // start the list scrolled to your own row
  useEffect(() => {
    const list = listRef.current, me = list?.querySelector("[data-me]");
    if (list && me) list.scrollTop = me.offsetTop - list.clientHeight / 2 + me.clientHeight / 2;
  }, [standings]);

  return (
    <section className="px-frame px-glow mx-auto mt-8 max-w-3xl bg-night-800/90 p-5 sm:p-7" style={{ "--frame": color }} aria-labelledby="board-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-wider text-muted">Four-week season · week {season.week}/{season.weeks}</p>
          <h2 id="board-title" className="mt-2 flex items-center gap-3 text-4xl" style={{ color }}>
            <RankGem name={rank.name} size={34} />
            {rank.name} league
          </h2>
          <p className="mt-1 text-sm text-muted">{season.start} – {season.end}</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted">Your place</p>
          <p className="text-4xl">{rank.position ? `#${rank.position}` : "—"}<span className="text-lg text-muted">/{rank.members}</span></p>
        </div>
      </div>
      <p className="mt-3 text-lg">{movementText(rank.movement)}</p>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 border-t-[3px] border-night-700 pt-3 text-sm text-muted">
        <span style={{ color: ZONES.promotion.color }}>▲ Moves up</span>
        <span style={{ color: ZONES.demotion.color }}>▼ Moves down</span>
        <span className="ml-auto">Top 20% move up · bottom 20% move down</span>
      </div>

      <ol ref={listRef} className="relative mt-3 max-h-[32rem] overflow-y-auto pr-1" aria-label={`${rank.name} league standings`}>
        {standings.map((player, i) => {
          const zone = player.zone ? ZONES[player.zone] : null;
          const medal = MEDALS[player.place];
          const promotionLine = player.zone === "promotion" && standings[i + 1]?.zone !== "promotion";
          const demotionLine = player.zone === "demotion" && standings[i - 1]?.zone !== "demotion";
          return (
            <li key={player.place}>
              {demotionLine && <ZoneLine color={ZONES.demotion.color} label="Demotion line" />}
              <div
                data-me={player.is_current_user || undefined}
                className={`flex items-center gap-3 border-l-4 px-3 py-2.5 ${player.is_current_user ? "bg-cyan/10" : i % 2 ? "bg-night-900/40" : ""}`}
                style={{ borderLeftColor: zone?.color ?? "transparent", ...(medal && !player.is_current_user ? { background: `${medal}14` } : {}) }}
              >
                <span className="w-12 shrink-0 text-right text-2xl tabular-nums" style={{ color: medal ?? "var(--color-muted)" }}>
                  {player.place}
                </span>
                <span className="text-2xl" aria-hidden="true">{emoji(player.avatar_id)}</span>
                <span className="min-w-0 flex-1 truncate text-xl" style={medal ? { color: medal } : undefined}>
                  {player.name}
                  {player.is_current_user && <span className="px-frame ml-2 px-1.5 align-middle text-sm text-cyan [--frame:var(--color-cyan)]">YOU</span>}
                </span>
                {zone && <span className="shrink-0 text-sm" style={{ color: zone.color }}>{zone.label}</span>}
              </div>
              {promotionLine && <ZoneLine color={ZONES.promotion.color} label="Promotion line" />}
            </li>
          );
        })}
        {!standings.length && <li className="py-8 text-center text-muted">You'll appear here after logging enough for a HealthScore.</li>}
      </ol>
      <p className="mt-4 text-sm text-muted">
        Standings reflect HealthScore and consistency and refresh as players check in; the exact scoring stays behind the scenes.
        Ranks change when the season closes.
      </p>
    </section>
  );
}

function ZoneLine({ color, label }) {
  return (
    <div className="flex items-center gap-2 py-1 text-xs uppercase tracking-wider" style={{ color }} aria-hidden="true">
      <span className="h-0 flex-1 border-t-2 border-dashed" style={{ borderColor: color }} />
      {label}
      <span className="h-0 flex-1 border-t-2 border-dashed" style={{ borderColor: color }} />
    </div>
  );
}

function RankLadder({ leagues, current, share }) {
  return (
    <section className="mt-12" aria-labelledby="ranks-title">
      <p className="text-sm uppercase tracking-[0.2em] text-gold">Climb the ladder</p>
      <h2 id="ranks-title" className="mt-2 text-3xl sm:text-4xl">League ranks</h2>
      <p className="mt-2 max-w-3xl text-muted">
        Everyone starts in Bronze. When each four-week season closes, the top {Math.round(share * 100)}% of a league move up a rank
        and the bottom {Math.round(share * 100)}% move down; leagues with fewer than 5 players hold.
      </p>
      <ol className="mt-6 grid grid-cols-3 gap-3 sm:grid-cols-5 lg:grid-cols-9">
        {leagues.map((name, i) => {
          const here = i === current, color = RANK_COLORS[name];
          return (
            <li
              key={name}
              aria-current={here ? "true" : undefined}
              className={`px-frame flex flex-col items-center gap-2 px-2 py-4 text-center ${here ? "px-glow bg-night-700/80" : "bg-night-800/90"}`}
              style={{ "--frame": here ? color : "var(--color-night-600)" }}
            >
              <RankGem name={name} size={40} />
              <span className="text-lg leading-tight" style={{ color }}>{name}</span>
              <span className="text-xs text-muted">Rank {i + 1}</span>
              {here && <span className="text-xs tracking-wider text-cyan">YOU ARE HERE</span>}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function GamificationPanel({ userId }) {
  const [data, setData] = useState(EMPTY);
  const [state, setState] = useState("loading");
  const [busyAvatar, setBusyAvatar] = useState(null);
  const [message, setMessage] = useState(null);
  const previousCoins = useRef(null);
  const [reward, setReward] = useState(null);

  async function reload(showReward = false) {
    setState("loading");
    try {
      const [league, inventory, status] = await Promise.all([
        getLeague(userId), getAvatarInventory(userId), getGamification(userId),
      ]);
      if (showReward && previousCoins.current !== null && inventory.fitcoins > previousCoins.current) {
        setReward(inventory.fitcoins - previousCoins.current);
        window.setTimeout(() => setReward(null), 2400);
      }
      previousCoins.current = inventory.fitcoins;
      setData({ league, inventory, status });
      setMessage(null); // an earlier load error no longer applies
      setState("ready");
    } catch (error) {
      setMessage({ ok: false, text: error.message });
      setState("error");
    }
  }

  useEffect(() => { reload(false); }, [userId]);

  async function doAvatarAction(avatar) {
    setBusyAvatar(avatar.id);
    setMessage(null);
    try {
      if (avatar.owned) await equipAvatar(userId, avatar.id);
      else await purchaseAvatar(userId, avatar.id);
      await reload(false);
      setMessage({ ok: true, text: avatar.owned ? `${avatar.name} equipped.` : `${avatar.name} unlocked.` });
    } catch (error) {
      setMessage({ ok: false, text: error.message });
    } finally {
      setBusyAvatar(null);
    }
  }

  const { inventory, league } = data;
  const equippedEmoji = inventory?.avatars?.find((avatar) => avatar.id === inventory.equipped_avatar)?.emoji || "🧑‍🚀";

  return (
    <section className="mt-10" aria-labelledby="game-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-gold">Your game layer</p>
          <h1 id="game-title" className="mt-2 text-5xl sm:text-6xl">League</h1>
        </div>
        <div className="relative flex items-center gap-3 px-frame bg-night-800/90 px-5 py-3 [--frame:var(--color-gold)]">
          <span className="text-3xl" aria-label="Equipped avatar">{equippedEmoji}</span>
          <div>
            <p className="mb-1 text-xs uppercase tracking-wider text-muted">Level {data.status?.level ?? 1}</p>
            <FitCoin amount={inventory?.fitcoins ?? data.status?.fitcoins ?? 0} animate={reward !== null} />
          </div>
          {reward !== null && (
            <motion.span
              initial={{ opacity: 0, y: 12, scale: 0.8 }} animate={{ opacity: 1, y: -22, scale: 1 }}
              className="absolute -top-3 right-4 whitespace-nowrap text-lg font-bold text-gold drop-shadow-[0_2px_8px_#000]"
              role="status"
            >+{reward} FitCoins</motion.span>
          )}
        </div>
      </div>

      {state === "loading" && !league && <p role="status" className="mt-5 text-muted">Loading your league and rewards…</p>}
      {state === "error" && (
        <div role="alert" className="px-frame mt-5 flex flex-wrap items-center justify-between gap-3 bg-night-800/90 px-4 py-3 [--frame:var(--color-nutrition)]">
          <span>{message?.text || "Couldn't load rewards."}</span>
          <button type="button" className="px-focus text-cyan" onClick={() => reload(false)}>Try again</button>
        </div>
      )}

      {league && inventory && (
        <>
          <Leaderboard league={league} avatars={inventory.avatars} />

          <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <section className="px-frame bg-night-800/90 p-5 [--frame:var(--color-sleep)]">
              <h2 className="text-xl font-bold">Streaks & badges</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {(inventory.streaks || []).length ? inventory.streaks.map((streak) => (
                  <span key={streak.streak_type} className="border border-night-600 px-3 py-2 text-muted">
                    🔥 {STREAK_LABELS[streak.streak_type] || streak.streak_type}: <b className="text-ink">{streak.current_streak} day{streak.current_streak === 1 ? "" : "s"}</b>
                  </span>
                )) : <span className="text-muted">Log progress on consecutive days to start a streak.</span>}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {(inventory.badges || []).length ? inventory.badges.map((badge) => (
                  <span key={badge.badge_id} title={badge.description} className="border border-gold/50 bg-[#473416]/40 px-3 py-2 text-gold">✦ {badge.name.replaceAll("_", " ")}</span>
                )) : <span className="text-muted">Milestone badges add FitCoins to your wallet.</span>}
              </div>
            </section>

            <section className="px-frame bg-night-800/90 p-5 sm:p-6 [--frame:var(--color-gold)]">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-wider text-gold">FitCoin shop</p>
                  <h2 className="mt-1 text-2xl font-bold">Choose your avatar</h2>
                </div>
                <FitCoin amount={inventory.fitcoins} />
              </div>
              <div className="mt-5 grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
                {inventory.avatars.map((avatar) => (
                  <article key={avatar.id} className={`border p-4 text-center ${avatar.equipped ? "border-cyan bg-cyan/10" : "border-night-700 bg-night-900/45"}`}>
                    <div className="text-5xl" aria-hidden="true">{avatar.emoji}</div>
                    <h3 className="mt-2 text-lg font-bold">{avatar.name}</h3>
                    <p className="mt-1 text-sm text-gold">{avatar.cost === 0 ? "FREE" : `${avatar.cost} FitCoins`}</p>
                    <button
                      type="button" disabled={busyAvatar !== null || avatar.equipped}
                      onClick={() => doAvatarAction(avatar)}
                      className={`px-focus mt-3 w-full border px-2 py-2 text-sm ${avatar.equipped ? "border-cyan text-cyan" : avatar.owned ? "border-night-500 text-ink hover:border-cyan" : "border-gold text-gold hover:bg-[#473416]/50"}`}
                    >
                      {busyAvatar === avatar.id ? "Saving…" : avatar.equipped ? "Equipped" : avatar.owned ? "Equip" : "Unlock"}
                    </button>
                  </article>
                ))}
              </div>
              {message?.ok && <p role="status" className="mt-4 text-activity">{message.text}</p>}
              {message && !message.ok && state === "ready" && <p role="alert" className="mt-4 text-nutrition">{message.text}</p>}
            </section>
          </div>

          <RankLadder leagues={league.leagues ?? Object.keys(RANK_COLORS)} current={league.league.tier} share={league.promotion_share ?? 0.2} />
        </>
      )}
    </section>
  );
}

export default GamificationPanel;
