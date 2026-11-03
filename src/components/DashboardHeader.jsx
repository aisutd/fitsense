import { Logo } from "../ScreenLayout";

function DashboardHeader({ activeTab, onTabChange, onLogout }) {
  const tabs = [
    { id: "health", label: "HealthScore" },
    { id: "plan", label: "Plan" },
    { id: "forecast", label: "Forecast" },
  ];

  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <Logo />
      <nav aria-label="Dashboard" className="order-3 flex w-full gap-2 sm:order-2 sm:w-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            aria-current={activeTab === tab.id ? "page" : undefined}
            onClick={() => tab.id !== activeTab && onTabChange(tab.id)}
            className={`px-focus border-b-[3px] px-3 py-2 text-lg transition-colors sm:px-4 ${
              activeTab === tab.id
                ? "border-cyan text-cyan"
                : "border-transparent text-muted hover:border-night-500 hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <button
        type="button"
        onClick={onLogout}
        className="px-focus order-2 text-lg text-muted transition-colors hover:text-cyan sm:order-3"
      >
        Log out ⏻
      </button>
    </header>
  );
}

export default DashboardHeader;
