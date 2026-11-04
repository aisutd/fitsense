import DashboardHeader from "../components/DashboardHeader";
import GamificationPanel from "../components/GamificationPanel";

// The game layer on its own tab: league standing and season podium, streaks and badges, and the
// FitCoin avatar shop.
function League({ userId, onNavigate, onLogout }) {
  return (
    <main className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-8 sm:pt-10">
      <DashboardHeader activeTab="league" onTabChange={onNavigate} onLogout={onLogout} />
      <GamificationPanel userId={userId} page />
    </main>
  );
}

export default League;
