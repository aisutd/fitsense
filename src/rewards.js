// Reward pop-ups: anything that logs progress calls celebrate() with the API result, and the
// RewardLayer (mounted once in App) plays the effects. They get bigger with the daily check-in
// streak (consecutive days with anything logged), which recovery days don't break.

const listeners = new Set();
let nextId = 0;

// Each tier adds to the one before it. min = streak days, including today.
export const STREAK_TIERS = [
  { min: 1, name: "Spark" },        // a sparkle burst
  { min: 3, name: "Glow" },         // gold, with a coin fountain for FitCoins
  { min: 5, name: "Combo" },        // a streak counter slams in
  { min: 7, name: "Party" },        // confetti
  { min: 14, name: "Legend" },      // confetti from both sides, brighter, bigger
];

export function tierFor(streak) {
  let index = 0;
  STREAK_TIERS.forEach((tier, i) => {
    if (streak >= tier.min) index = i;
  });
  return index;
}

/** "2 more days to Combo", or null at the top tier. */
export function nextTierHint(streak) {
  const next = STREAK_TIERS[tierFor(streak) + 1];
  if (!next) return null;
  const left = next.min - Math.max(streak, 0);
  return `${left} more day${left === 1 ? "" : "s"} to ${next.name}`;
}

export function onCelebrate(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * result: a log endpoint's response ({ rewards, checkin_streak }). anchor: the element the effect
 * bursts from (usually the button that was pressed). Does nothing when nothing was earned.
 */
export function celebrate(result, anchor) {
  const reward = result?.rewards;
  if (!reward?.points_awarded && !reward?.fitcoins_awarded && !reward?.badges_earned?.length) return;
  const rect = anchor?.isConnected ? anchor.getBoundingClientRect() : null;
  const point = rect && rect.width
    ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
    : { x: window.innerWidth / 2, y: window.innerHeight * 0.6 };
  const event = { id: ++nextId, reward, streak: result.checkin_streak ?? 0, point };
  listeners.forEach((listener) => listener(event));
}
