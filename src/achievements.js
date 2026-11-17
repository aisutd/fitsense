// The System's achievement announcements. Any API response with an `achievements` list (logs, the
// league, the shop, avatar changes) is passed to announce() by api.js, and the Announcer (mounted
// once in App) shows them one at a time. The list on the League tab comes back under `items`, so it
// isn't announced again.

const listeners = new Set();
let nextId = 0;

export const RARITY = {
  common: { label: "Common", color: "#c9d2e3" },
  uncommon: { label: "Uncommon", color: "#42e08b" },
  rare: { label: "Rare", color: "#4fd8ff" },
  epic: { label: "Epic", color: "#c77dff" },
  legendary: { label: "Legendary", color: "#f7b733" },
};

export function onAnnounce(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function announce(achievements) {
  if (!achievements?.length) return;
  const items = achievements.map((a) => ({ ...a, id: ++nextId }));
  listeners.forEach((listener) => listener(items));
  window.dispatchEvent(new CustomEvent("fitsense:achievements"));   // lets the League tab refresh its list
}

// "snarky" (the System's commentary) or "plain" (just what it was for). Kept per browser.
const MODE_KEY = "fitsense.announcer";

export function announcerMode() {
  try {
    return localStorage.getItem(MODE_KEY) === "plain" ? "plain" : "snarky";
  } catch {
    return "snarky";
  }
}

export function setAnnouncerMode(mode) {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    // storage blocked: the choice lasts until the page reloads
  }
  window.dispatchEvent(new CustomEvent("fitsense:announcer-mode", { detail: mode }));
}

/** "Reward: 40 FitCoins · 60 XP", or the System declining. */
export function rewardLine(a) {
  if (!a.rewarded) return "Reward: none. The System doesn't reward that.";
  if (!a.reward) return "Already earned. No second reward.";
  return `Reward: ${a.reward.fitcoins} FitCoins · ${a.reward.xp} XP`;
}
