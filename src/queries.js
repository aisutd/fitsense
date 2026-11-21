import {
  getAchievements, getAvatarInventory, getCurrentPlan, getForecasts, getGamification, getGoals, getHealthScore, getLeague,
} from "./api";

// Each screen's data as a cached query ({ key, load }, see queryCache.js), so screens and the
// background prefetch (App, after the dashboard loads) share one cache entry per player.

export const queries = {
  healthScore: (userId, date) => ({ key: `healthscore:${userId}:${date}`, load: () => getHealthScore(userId, "day", date) }),
  plan: (userId) => ({ key: `plan:${userId}`, load: () => getCurrentPlan(userId) }),
  forecast: (userId) => ({ key: `forecast:${userId}`, load: () => getForecasts(userId) }),
  goals: (userId) => ({ key: `goals:${userId}`, load: () => getGoals(userId) }),
  league: (userId) => ({
    key: `league:${userId}`,
    load: () => Promise.all([getLeague(userId), getAvatarInventory(userId), getGamification(userId)])
      .then(([league, inventory, status]) => ({ league, inventory, status })),
  }),
  achievements: (userId) => ({ key: `achievements:${userId}`, load: () => getAchievements(userId) }),
};
