import { useCallback, useState } from "react";
import { useLenis } from "lenis/react";
import PixelBackground from "./components/PixelBackground";
import PixelTransition from "./components/PixelTransition";
import { NameGreeting, Information, GoalScreen, Proficiency, WorkoutDays, WorkoutLocation } from "./screens/Onboarding";
import HealthScore from "./screens/HealthScore";
import { supabase } from "./supabaseClient";

const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function App() {
  const [screen, setScreen] = useState(1);
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

    const { error } = await supabase.from("users").insert({
      name: name,
      age: age,
      weight_lbs: weight,
      height_feet: feet,
      height_inches: inches,
      goal: goal,
      proficiency: proficiency,
      workout_days: workoutDays,
      workout_location: workoutLocation,
    });

    console.log("insert error:", error);

    setSaving(false);

    if (error) {
      setSaveError("Couldn't save your profile. Please try again.");
      return;
    }

    goTo(7);
  }

  const back = () => goTo(screen - 1);

  let content;
  if (screen === 1) {
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
  } else {
    content = (
      <HealthScore
        profile={{ name, age, weight, feet, inches, goal, proficiency, workoutDays, workoutLocation }}
        onEditProfile={() => goTo(1)}
      />
    );
  }

  return (
    <div className="scanlines relative min-h-screen font-pixel text-ink">
      <PixelBackground />
      {/* key remounts the screen so its entrance animation replays */}
      <div key={screen}>{content}</div>
      <PixelTransition phase={phase} onCovered={handleCovered} onRevealed={handleRevealed} />
    </div>
  );
}

export default App;
