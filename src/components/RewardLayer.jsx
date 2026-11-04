import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import PixelFx from "./PixelFx";
import { nextTierHint, onCelebrate, STREAK_TIERS, tierFor } from "../rewards";
import * as collectBurst from "../fx/pixelfx/fx/pickups/collect-burst.js";
import * as coinCollect from "../fx/pixelfx/fx/ui/coin-collect.js";
import * as comboCounter from "../fx/pixelfx/fx/ui/combo-counter.js";
import * as confetti from "../fx/pixelfx/fx/ui/confetti.js";
import * as achievement from "../fx/pixelfx/fx/ui/achievement.js";

// Plays the reward pop-ups from celebrate() (src/rewards.js) over everything else. Effects stack up
// with the check-in streak; badges and level-ups get their own toast after. With reduced motion on,
// only the text shows, without movement.

const CYAN = ["#04121c", "#08263a", "#0e4566", "#13709e", "#1fa3d6", "#4fd8ff", "#b8f1ff", "#ffffff"];
const GOLD = ["#2a1405", "#5c3008", "#9a5a0e", "#d48e18", "#f5b92c", "#ffde5e", "#fff4bc", "#ffffff"];
const PINK = ["#1a0516", "#3d0a33", "#701560", "#b0228f", "#f53cd1", "#ff86e6", "#ffd2f6", "#ffffff"];
const GREEN = ["#04160c", "#0a2e18", "#12502a", "#1b7a3e", "#2aae58", "#42e08b", "#b6f7d2", "#ffffff"];
const BURST = [CYAN, GOLD, GOLD, GOLD, GREEN];
const COMBO = [null, null, PINK, GOLD, GREEN];
const MAX_COINS = 12;
const TOAST_GAP = 2.3; // seconds between badge / level-up toasts
const TEXT_SECONDS = 2.2;
const TEXT_MARGIN = 150; // keeps the centered reward text on screen near the edges

// keep an effect's canvas on screen: x is where its origin goes
function clampX(effect, x, scale, width) {
  const [w] = effect.meta.size, [ox] = effect.meta.origin;
  return Math.min(Math.max(x, ox * scale + 4), width - (w - ox) * scale - 4);
}

// the toast's plate fits about 12 letters
const BADGE_LABELS = { first_workout: "1ST WORKOUT", ten_workouts: "10 WORKOUTS", seven_day_streak: "7-DAY STREAK" };
const label = (id) => BADGE_LABELS[id] ?? id.replaceAll("_", " ").toUpperCase().slice(0, 12);

/** The effects for one reward: [{ effect, options, x, y, scale, delay }]. */
function effectsFor({ reward, streak, point }, width, height) {
  const tier = tierFor(streak);
  const list = [];
  const add = (effect, options, x, y, scale, delay = 0) =>
    list.push({ effect, options, x: clampX(effect, x, scale, width), y, scale, delay });

  add(collectBurst, { palette: BURST[tier], light: tier >= 4 ? 1.5 : 1, seed: streak + 3 }, point.x, point.y + 20, tier >= 4 ? 3 : 2);

  const coins = Math.min(reward.fitcoins_awarded ?? 0, MAX_COINS);
  if (tier >= 1 && coins > 0) {
    const balance = reward.fitcoins_balance ?? coins;
    add(coinCollect, { count: coins, from: Math.max(0, balance - coins), seed: streak }, point.x, point.y + 30, 2, 0.15);
  }
  if (tier >= 2) {
    add(comboCounter, { count: streak, label: "DAY STREAK", palette: COMBO[tier], seed: streak },
        width / 2, Math.min(height * 0.3, 230), width < 560 ? 2 : 3, 0.3);
  }
  if (tier >= 3) {
    const scale = Math.max(2, Math.min(4, Math.floor(width / 220)));
    if (tier >= 4) {
      add(confetti, { seed: 11 }, width * 0.28, height - 6, scale, 0.45);
      add(confetti, { seed: 23 }, width * 0.72, height - 6, scale, 0.7);
    } else {
      add(confetti, { seed: streak }, width / 2, height - 6, scale, 0.45);
    }
  }

  const toasts = [
    ...(reward.badges_earned ?? []).map((badge) => ({ title: "BADGE", text: label(badge.id) })),
    ...(reward.level > reward.previous_level ? [{ title: "LEVEL UP", text: `LEVEL ${reward.level}` }] : []),
  ];
  const toastScale = Math.max(1, Math.min(3, Math.floor((width - 32) / 220)));
  toasts.forEach((toast, i) =>
    add(achievement, { ...toast, seed: i + 9 }, width / 2, 96, toastScale, (tier >= 2 ? 1.2 : 0.6) + i * TOAST_GAP));
  return list;
}

function RewardText({ celebration, still }) {
  const { reward, streak, point } = celebration;
  const tier = STREAK_TIERS[tierFor(streak)];
  const hint = nextTierHint(streak);
  return (
    <motion.div
      initial={still ? { opacity: 0 } : { opacity: 0, y: 0, scale: 0.6 }}
      animate={still ? { opacity: [0, 1, 1, 0] } : { opacity: [0, 1, 1, 0], y: [-10, -54, -70, -84], scale: [0.6, 1.1, 1, 1] }}
      transition={{ duration: TEXT_SECONDS, times: [0, 0.15, 0.75, 1], ease: "easeOut" }}
      className="pointer-events-none absolute -translate-x-1/2 -translate-y-full whitespace-nowrap text-center"
      style={{ left: Math.min(Math.max(point.x, TEXT_MARGIN), window.innerWidth - TEXT_MARGIN), top: point.y, textShadow: "2px 2px 0 #050912, -1px -1px 0 #050912" }}
    >
      <p className="font-title text-3xl leading-none">
        {reward.points_awarded > 0 && <span className="text-cyan">+{reward.points_awarded} XP</span>}
        {reward.points_awarded > 0 && reward.fitcoins_awarded > 0 && " "}
        {reward.fitcoins_awarded > 0 && <span className="text-gold">+{reward.fitcoins_awarded} FitCoins</span>}
      </p>
      {streak > 0 && (
        <p className="mt-1 text-lg text-ink">
          🔥 {streak}-day streak · <span className="text-gold">{tier.name}</span>
          {hint && <span className="block text-sm text-muted">{hint}</span>}
        </p>
      )}
    </motion.div>
  );
}

function RewardLayer() {
  const [celebrations, setCelebrations] = useState([]);
  const still = useReducedMotion();

  useEffect(() => onCelebrate((event) => {
    const width = window.innerWidth, height = window.innerHeight;
    const effects = still ? [] : effectsFor(event, width, height);
    const seconds = Math.max(TEXT_SECONDS, ...effects.map((e) => e.delay + e.effect.meta.duration)) + 0.3;
    setCelebrations((list) => [...list, { ...event, effects }]);
    window.setTimeout(() => setCelebrations((list) => list.filter((c) => c.id !== event.id)), seconds * 1000);
  }), [still]);

  if (!celebrations.length) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden" aria-hidden="true">
      {celebrations.map((celebration) => (
        <div key={celebration.id}>
          {celebration.effects.map((e, i) => (
            <PixelFx key={i} effect={e.effect} options={e.options} x={e.x} y={e.y} scale={e.scale} delay={e.delay} />
          ))}
          <RewardText celebration={celebration} still={still} />
        </div>
      ))}
    </div>
  );
}

export default RewardLayer;
