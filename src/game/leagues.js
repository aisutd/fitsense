// Look of each league (tier 0-8, same order as LEAGUES in backend/app/gamification.py).
// color = main hue, light = highlight, deep = shadow, bg = tinted base; item = the avatar
// accessory that league unlocks (they stack as you climb).
export const LEAGUE_STYLES = [
  { name: "Bronze", numeral: "I", color: "#ff8a3d", light: "#ffc58f", deep: "#7a3410", bg: "#2a1408", item: "wristband" },
  { name: "Bronze Premium", numeral: "II", color: "#ff7a2e", light: "#ffd0a0", deep: "#8a2f05", bg: "#301206", item: "headband" },
  { name: "Silver", numeral: "III", color: "#b9c8ff", light: "#eef2ff", deep: "#3e4a7a", bg: "#141c36", item: "gym towel" },
  { name: "Silver Premium", numeral: "IV", color: "#d4dcff", light: "#ffffff", deep: "#4a5590", bg: "#18203e", item: "gloves" },
  { name: "Gold", numeral: "V", color: "#ffc61a", light: "#fff1a8", deep: "#8a5a00", bg: "#2e2104", item: "medal" },
  { name: "Platinum", numeral: "VI", color: "#2cf5d0", light: "#c8fff4", deep: "#0a6b5c", bg: "#062a26", item: "lifting belt" },
  { name: "Ruby", numeral: "VII", color: "#ff2e63", light: "#ffb3c7", deep: "#7a0626", bg: "#30061a", item: "cape" },
  { name: "Diamond", numeral: "VIII", color: "#4fe3ff", light: "#e6fbff", deep: "#0d5c80", bg: "#06243a", item: "shades" },
  { name: "Sapphire", numeral: "IX", color: "#4d6bff", light: "#c9d4ff", deep: "#1a1f8a", bg: "#0e1040", item: "crown" },
];

export const leagueStyle = (tier) => LEAGUE_STYLES[Math.max(0, Math.min(LEAGUE_STYLES.length - 1, Number(tier) || 0))];

// profile.fitness_level -> how it's shown on the banner
export const FITNESS_LEVELS = {
  beginner: { label: "Beginner", short: "BEG", color: "#42e08b" },
  intermediate: { label: "Intermediate", short: "INT", color: "#4fd8ff" },
  advanced: { label: "Advanced", short: "ADV", color: "#c77dff" },
};

export const fitnessLevel = (level) => FITNESS_LEVELS[String(level || "").toLowerCase()] || FITNESS_LEVELS.beginner;
