import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { useLenis } from "lenis/react";
import PixelBackground from "./components/PixelBackground";
import PixelTransition from "./components/PixelTransition";
import RewardLayer from "./components/RewardLayer";
import HeartbeatBackdrop from "./components/HeartbeatBackdrop";
import Announcer from "./components/Announcer";
import { DemoDateBanner } from "./components/DemoDate";
import { NameGreeting, Information, GoalScreen, Proficiency, WorkoutDays, WorkoutLocation } from "./screens/Onboarding";
import HealthScore from "./screens/HealthScore";
import Auth from "./screens/Auth";
import { fromApiProfile, getProfile, localToday, profileErrorMessage, saveProfile, toApiProfile } from "./api";
import { queries } from "./queries";
import { clearQueryCache, prefetch } from "./queryCache";

// The other tabs load as separate chunks, fetched in the background once the dashboard is up
// (warmUpTabs), so the first screen loads less and the tabs still open without waiting.
const loadForecast = () => import("./screens/Forecast");
const loadLeague = () => import("./screens/League");
const loadPlan = () => import("./screens/WorkoutPlan");
const Forecast = lazy(loadForecast);
const League = lazy(loadLeague);
const WorkoutPlan = lazy(loadPlan);
const WARM_UP_DELAY = 1200;   // ms after the dashboard shows, so the first screen's own requests go first

function warmUpTabs(userId) {
  [loadPlan, loadForecast, loadLeague].forEach((load) => load().catch(() => {}));
  [queries.plan(userId), queries.forecast(userId), queries.goals(userId), queries.league(userId),
    queries.achievements(userId)].forEach(prefetch);
}

// Screens: -1 log in / sign up, 0 loading the player, 1-6 onboarding, 7 HealthScore, 8 Forecast, 9 Plan.
const AUTH = -1;
const LOADING = 0;
const DASHBOARD = 7;
const FORECAST = 8;
const PLAN = 9;
const LEAGUE = 10;
const TAB_SCREENS = { health: DASHBOARD, forecast: FORECAST, plan: PLAN, league: LEAGUE };

const USER_KEY = "fitsense:userId";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Stay logged in on this device until the player logs out.
function savedUserId() {
  try {
    const saved = localStorage.getItem(USER_KEY);
    return saved && UUID_RE.test(saved) ? saved : null;
  } catch {
    return null;
  }
}

function rememberUser(id) {
  try {
    if (id) localStorage.setItem(USER_KEY, id);
    else localStorage.removeItem(USER_KEY);
  } catch {
    // Private mode etc.: still works, just won't stay logged in after a reload.
  }
}

const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function App() {
  const [userId, setUserId] = useState(savedUserId);
  const [screen, setScreen] = useState(userId ? LOADING : AUTH);
  const [phase, setPhase] = useState("idle"); // idle | covering | revealing
  const [pendingScreen, setPendingScreen] = useState(null);
  const lenis = useLenis();

  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [proficiency, setProficiency] = useState("");
  const [workoutDays, setWorkoutDays] = useState("");
  const [workoutLocation, setWorkoutLocation] = useState("");
  const [age, setAge] = useState("");
  const [weight, setWeight] = useState("");
  const [feet, setFeet] = useState("");
  const [inches, setInches] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  function applyProfile(p) {
    setName(p.name);
    setAge(p.age);
    setWeight(p.weight);
    setFeet(p.feet);
    setInches(p.inches);
    setGoal(p.goal);
    setProficiency(p.proficiency);
    setWorkoutDays(p.workoutDays);
    setWorkoutLocation(p.workoutLocation);
  }

  // Load the logged-in player's profile, then show the dashboard (whose HealthScore starts loading
  // at the same time, rather than after the profile).
  useEffect(() => {
    if (screen !== LOADING) return;
    let cancelled = false;
    prefetch(queries.healthScore(userId, localToday()));
    getProfile(userId)
      .then((p) => {
        if (cancelled) return;
        applyProfile(fromApiProfile(p));
        setScreen(DASHBOARD);
      })
      .catch((error) => {
        if (cancelled) return;
        if (error.status === 404) {
          setScreen(1); // account exists but onboarding was never finished
        } else {
          logOutNow();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [screen, userId]);

  function resetProfile() {
    applyProfile({ name: "", age: "", weight: "", feet: "", inches: "", goal: "", proficiency: "", workoutDays: "", workoutLocation: "" });
    setSaveError("");
  }

  function handleAuthenticated(account) {
    setUserId(account.user_id);
    rememberUser(account.user_id);
    resetProfile();
    if (account.has_profile) {
      goTo(LOADING);
    } else {
      setName(account.username);
      goTo(1);
    }
  }

  // Once the dashboard is up, quietly load the other tabs (their code and data).
  const onDashboard = screen >= DASHBOARD && Boolean(userId);
  useEffect(() => {
    if (!onDashboard) return undefined;
    const timer = window.setTimeout(() => warmUpTabs(userId), WARM_UP_DELAY);
    return () => window.clearTimeout(timer);
  }, [onDashboard, userId]);

  function logOutNow() {
    clearQueryCache();
    rememberUser(null);
    setUserId(null);
    resetProfile();
    setScreen(AUTH);
  }

  function handleLogout() {
    clearQueryCache();
    rememberUser(null);
    setUserId(null);
    goTo(AUTH);
  }

  // Move to another screen behind the pixel dissolve.
  function goTo(next) {
    if (phase !== "idle") return;
    if (prefersReducedMotion()) {
      setScreen(next);
      lenis?.scrollTo(0, { immediate: true });
      return;
    }
    setPendingScreen(next);
    setPhase("covering");
  }

  const handleCovered = useCallback(() => {
    setScreen(pendingScreen);
    lenis?.scrollTo(0, { immediate: true });
    setPhase("revealing");
  }, [pendingScreen, lenis]);

  const handleRevealed = useCallback(() => {
    setPendingScreen(null);
    setPhase("idle");
  }, []);

  async function handleWorkoutLocationContinue() {
    setSaving(true);
    setSaveError("");

    // The profile uses the account's id, so logging in finds it again.
    const id = userId ?? crypto.randomUUID();
    try {
      await saveProfile(
        id,
        toApiProfile({ name, age, weight, feet, inches, goal, proficiency, workoutDays, workoutLocation })
      );
    } catch (error) {
      setSaveError(profileErrorMessage(error));
      setSaving(false);
      return;
    }

    setUserId(id);
    rememberUser(id);
    setSaving(false);
    goTo(DASHBOARD);
  }

  const back = () => goTo(screen - 1);

  let content;
  if (screen === AUTH) {
    content = <Auth onAuthenticated={handleAuthenticated} />;
  } else if (screen === LOADING) {
    content = (
      <p role="status" className="relative z-10 flex min-h-screen items-center justify-center text-2xl text-muted">
        Loading player...
      </p>
    );
  } else if (screen === 1) {
    content = <NameGreeting name={name} setName={setName} onContinue={() => goTo(2)} />;
  } else if (screen === 2) {
    content = (
      <Information
        name={name}
        age={age}
        setAge={setAge}
        weight={weight}
        setWeight={setWeight}
        feet={feet}
        setFeet={setFeet}
        inches={inches}
        setInches={setInches}
        onContinue={() => goTo(3)}
        onBack={back}
      />
    );
  } else if (screen === 3) {
    content = <GoalScreen goal={goal} setGoal={setGoal} onContinue={() => goTo(4)} onBack={back} />;
  } else if (screen === 4) {
    content = <Proficiency proficiency={proficiency} setProficiency={setProficiency} onContinue={() => goTo(5)} onBack={back} />;
  } else if (screen === 5) {
    content = <WorkoutDays workoutDays={workoutDays} setWorkoutDays={setWorkoutDays} onContinue={() => goTo(6)} onBack={back} />;
  } else if (screen === 6) {
    content = (
      <WorkoutLocation
        workoutLocation={workoutLocation}
        setWorkoutLocation={setWorkoutLocation}
        onContinue={handleWorkoutLocationContinue}
        onBack={back}
        saving={saving}
        saveError={saveError}
      />
    );
  } else if (screen === DASHBOARD) {
    content = (
      <HealthScore
        userId={userId}
        profile={{ name, age, weight, feet, inches, goal, proficiency, workoutDays, workoutLocation }}
        onEditProfile={() => goTo(1)}
        onLogout={handleLogout}
        onNavigate={(tab) => goTo(TAB_SCREENS[tab])}
      />
    );
  } else if (screen === LEAGUE) {
    content = <League userId={userId} onLogout={handleLogout} onNavigate={(tab) => goTo(TAB_SCREENS[tab])} />;
  } else if (screen === PLAN) {
    content = (
      <WorkoutPlan
        userId={userId}
        profile={{ name }}
        onEditProfile={() => goTo(1)}
        onLogout={handleLogout}
        onNavigate={(tab) => goTo(TAB_SCREENS[tab])}
      />
    );
  } else {
    content = (
      <Forecast
        userId={userId}
        profile={{ name, age, weight, feet, inches, goal, proficiency, workoutDays, workoutLocation }}
        onNavigate={(tab) => goTo(TAB_SCREENS[tab])}
        onEditProfile={() => goTo(1)}
        onLogout={handleLogout}
      />
    );
  }

  return (
    <div className="scanlines relative min-h-screen font-pixel text-ink">
      <PixelBackground />
      <HeartbeatBackdrop />
      {/* key remounts the screen so its entrance animation replays */}
      <div key={screen}>
        <Suspense fallback={<p role="status" className="relative z-10 p-10 text-lg text-muted">Loading…</p>}>{content}</Suspense>
      </div>
      <PixelTransition phase={phase} onCovered={handleCovered} onRevealed={handleRevealed} />
      <RewardLayer />
      <Announcer />
      <DemoDateBanner />
    </div>
  );
}

export default App;
