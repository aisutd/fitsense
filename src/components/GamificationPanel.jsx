import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { equipAvatar, getAvatarInventory, getGamification, getLeague, purchaseAvatar } from "../api";

const EMPTY = { league: null, inventory: null, status: null };
const STREAK_LABELS = { workout: "Workout", daily_goals: "Daily goals", sleep: "Sleep" };

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

function GamificationPanel({ userId, refreshKey = 0 }) {
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
      setState("ready");
    } catch (error) {
      setMessage({ ok: false, text: error.message });
      setState("error");
    }
  }

  useEffect(() => { reload(refreshKey > 0); }, [userId, refreshKey]);

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

  const inventory = data.inventory;
  const league = data.league;
  const currentTier = league?.league;
  const equippedEmoji = inventory?.avatars?.find((avatar) => avatar.id === inventory.equipped_avatar)?.emoji || "🧑‍🚀";

  return (
    <section className="mt-14" aria-labelledby="game-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-gold">Your game layer</p>
          <h2 id="game-title" className="mt-2 text-3xl font-bold sm:text-4xl">Leagues & FitCoins</h2>
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

      {state === "loading" && <p role="status" className="mt-5 text-muted">Loading your league and rewards…</p>}
      {state === "error" && (
        <div role="alert" className="px-frame mt-5 flex flex-wrap items-center justify-between gap-3 bg-night-800/90 px-4 py-3 [--frame:var(--color-nutrition)]">
          <span>{message?.text || "Couldn't load rewards."}</span>
          <button type="button" className="px-focus text-cyan" onClick={() => reload(false)}>Try again</button>
        </div>
      )}

      {state === "ready" && (
        <div className="mt-6 grid items-start gap-6 lg:grid-cols-[0.95fr_1.35fr]">
          <div className="grid gap-6">
            <section className="px-frame bg-night-800/90 p-5 sm:p-6 [--frame:var(--color-cyan)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-wider text-muted">Four-week season · week {league.season.week}/{league.season.weeks}</p>
                  <h3 className="mt-2 text-3xl font-bold text-cyan">{currentTier.name}</h3>
                </div>
                <div className="text-right">
                  <p className="text-sm text-muted">Your place</p>
                  <p className="text-3xl font-bold">{currentTier.position ? `#${currentTier.position}` : "—"}<span className="text-base text-muted">/{currentTier.members}</span></p>
                </div>
              </div>
              <p className="mt-3 text-muted">{currentTier.movement === "promotion zone" ? "You're on track to move up." : currentTier.movement === "demotion zone" ? "Keep your momentum to hold your league." : currentTier.movement === "building a league" ? "More players are needed before leagues can move." : currentTier.movement === "needs a HealthScore" ? "Log some activity to enter this season's standings." : "You're holding your current league position."}</p>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-night-700 pt-4 text-sm text-muted">
                <span>{league.season.start} — {league.season.end}</span>
                <span>Top 20% move up · bottom 20% move down</span>
              </div>
              <p className="mt-3 text-xs text-muted">Standings reflect HealthScore and consistency; the exact scoring formula stays behind the scenes.</p>
            </section>

            <section className="px-frame bg-night-800/90 p-5 [--frame:var(--color-sleep)]">
              <h3 className="text-xl font-bold">Streaks & badges</h3>
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
          </div>

          <section className="px-frame bg-night-800/90 p-5 sm:p-6 [--frame:var(--color-gold)]">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm uppercase tracking-wider text-gold">{currentTier.name} league</p>
                <h3 className="mt-1 text-2xl font-bold">Season podium</h3>
              </div>
              <span className="text-sm text-muted">Top 5</span>
            </div>
            <ol className="mt-4 grid gap-2">
              {league.podium.map((player) => (
                <li key={player.user_id} className={`flex items-center gap-3 border px-3 py-3 ${player.is_current_user ? "border-cyan bg-cyan/10" : "border-night-700 bg-night-900/50"}`}>
                  <span className={`w-9 text-center text-2xl font-bold ${player.place <= 3 ? "text-gold" : "text-muted"}`}>{["①", "②", "③", "④", "⑤"][player.place - 1]}</span>
                  <span className="text-3xl" aria-hidden="true">{inventory.avatars.find((avatar) => avatar.id === player.avatar_id)?.emoji || "🧑‍🚀"}</span>
                  <span className="min-w-0 flex-1 truncate text-xl">{player.name}{player.is_current_user ? " (you)" : ""}</span>
                  <span className="text-xs uppercase tracking-wider text-muted">{player.place === 1 ? "Champion" : `#${player.place}`}</span>
                </li>
              ))}
              {!league.podium.length && <li className="py-6 text-center text-muted">You’ll appear here after logging enough for a HealthScore.</li>}
            </ol>
            <p className="mt-4 text-sm text-muted">Standings refresh as players check in. Promotions and demotions are applied when the four-week season closes.</p>
          </section>

          <section className="px-frame bg-night-800/90 p-5 sm:p-6 lg:col-span-2 [--frame:var(--color-gold)]">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm uppercase tracking-wider text-gold">FitCoin shop</p>
                <h3 className="mt-1 text-2xl font-bold">Choose your avatar</h3>
              </div>
              <FitCoin amount={inventory.fitcoins} />
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {inventory.avatars.map((avatar) => (
                <article key={avatar.id} className={`border p-4 text-center ${avatar.equipped ? "border-cyan bg-cyan/10" : "border-night-700 bg-night-900/45"}`}>
                  <div className="text-5xl" aria-hidden="true">{avatar.emoji}</div>
                  <h4 className="mt-2 text-lg font-bold">{avatar.name}</h4>
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
            {message?.ok && state === "ready" && <p role="status" className="mt-4 text-activity">{message.text}</p>}
            {message && !message.ok && state === "ready" && <p role="alert" className="mt-4 text-nutrition">{message.text}</p>}
          </section>
        </div>
      )}
    </section>
  );
}

export default GamificationPanel;
