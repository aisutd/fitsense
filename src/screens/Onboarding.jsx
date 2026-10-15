import { motion } from "motion/react";
import ScreenLayout, { item } from "../ScreenLayout";
import ContinueButton from "../ContinueButton";
import OptionButton from "../OptionButton";
import PixelField from "../components/PixelField";
import PixelIcon from "../components/PixelIcon";
import { ICONS, levelIcon } from "../icons";

// Every screen is a <form> so pressing Enter continues, same as the button.
function submitWhen(valid, onContinue) {
  return (event) => {
    event.preventDefault();
    if (valid) onContinue();
  };
}

// SCREEN 1: NAME

export function NameGreeting({ name, setName, onContinue }) {
  const valid = name.trim() !== "";

  return (
    <ScreenLayout
      step={1}
      title={
        <>
          Press start,
          <br />
          <span className="text-activity">player one.</span>
        </>
      }
      subtitle="Let's start with the introduction! Build your profile and we'll turn it into your HealthScore."
    >
      <form onSubmit={submitWhen(valid, onContinue)}>
        <motion.div variants={item} className="mb-6 flex items-center gap-4">
          <PixelIcon icon={ICONS.player} size={48} />
          <p className="text-xl">What's your name?</p>
        </motion.div>

        <PixelField
          icon={ICONS.player}
          label="Player name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Type your name"
          autoFocus
          maxLength={40}
        />

        <ContinueButton show={valid} />
      </form>
    </ScreenLayout>
  );
}

// SCREEN 2: INFORMATION

export function Information({ name, age, setAge, weight, setWeight, feet, setFeet, inches, setInches, onContinue, onBack }) {
  const valid = Number(age) > 0 && Number(weight) > 0 && Number(feet) > 0;

  return (
    <ScreenLayout
      step={2}
      title={
        <>
          Welcome, <span className="text-cyan">{name}</span>!
        </>
      }
      subtitle="Enter your stats. We use them to tune your workouts and HealthScore."
      onBack={onBack}
    >
      <form onSubmit={submitWhen(valid, onContinue)} className="space-y-6">
        <PixelField
          icon={ICONS.hourglass}
          label="Age"
          type="number"
          inputMode="numeric"
          min={1}
          value={age}
          onChange={(e) => setAge(e.target.value)}
          placeholder="Enter your age"
          suffix="yrs"
          autoFocus
        />

        <PixelField
          icon={ICONS.kettlebell}
          label="Weight"
          type="number"
          inputMode="decimal"
          min={1}
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
          placeholder="Enter your weight"
          suffix="lbs"
        />

        <div>
          <motion.p variants={item} className="mb-2 flex items-center gap-2 text-sm uppercase tracking-wider text-muted">
            <PixelIcon icon={ICONS.ruler} size={18} />
            Height
          </motion.p>
          <div className="grid grid-cols-2 gap-4">
            <PixelField
              label="Feet"
              type="number"
              inputMode="numeric"
              min={1}
              value={feet}
              onChange={(e) => setFeet(e.target.value)}
              placeholder="5"
              suffix="ft"
            />
            <PixelField
              label="Inches"
              type="number"
              inputMode="numeric"
              min={0}
              max={11}
              value={inches}
              onChange={(e) => setInches(e.target.value)}
              placeholder="10"
              suffix="in"
            />
          </div>
        </div>

        <ContinueButton show={valid} />
      </form>
    </ScreenLayout>
  );
}

// SCREEN 3: FITNESS GOALS

const GOALS = [
  { name: "Lose Weight", description: "Lose weight and improve overall health.", icon: ICONS.flame, accent: "#ff5d6c" },
  { name: "Build Muscle", description: "Build muscle and increase strength.", icon: ICONS.dumbbell, accent: "#4d8dff" },
  { name: "Endurance", description: "Improve endurance and cardiovascular fitness.", icon: ICONS.heart, accent: "#a66bff" },
  { name: "General Fitness", description: "Maintain overall fitness and well-being.", icon: ICONS.star, accent: "#f7b733" },
];

export function GoalScreen({ goal, setGoal, onContinue, onBack }) {
  return (
    <ScreenLayout step={3} title="What's your fitness goal?" subtitle="Pick your main quest. You can change it later." onBack={onBack}>
      <form onSubmit={submitWhen(goal !== "", onContinue)}>
        <div className="grid gap-4 sm:grid-cols-2">
          {GOALS.map((g) => (
            <OptionButton
              key={g.name}
              label={g.name}
              description={g.description}
              icon={g.icon}
              accent={g.accent}
              selected={goal === g.name}
              onClick={() => setGoal(g.name)}
            />
          ))}
        </div>
        <ContinueButton show={goal !== ""} />
      </form>
    </ScreenLayout>
  );
}

// SCREEN 4: FITNESS PROFICIENCY

const LEVELS = [
  { name: "Beginner", description: "New to fitness and looking to get started.", bars: 1 },
  { name: "Intermediate", description: "Have some experience with fitness and looking to improve.", bars: 2 },
  { name: "Advanced", description: "Experienced in fitness and looking for advanced challenges.", bars: 3 },
];

export function Proficiency({ proficiency, setProficiency, onContinue, onBack }) {
  return (
    <ScreenLayout step={4} title="What's your fitness level?" subtitle="Choose your difficulty setting." onBack={onBack}>
      <form onSubmit={submitWhen(proficiency !== "", onContinue)} className="space-y-4">
        {LEVELS.map((level) => (
          <OptionButton
            key={level.name}
            label={level.name}
            description={level.description}
            icon={levelIcon(level.bars)}
            selected={proficiency === level.name}
            onClick={() => setProficiency(level.name)}
          />
        ))}
        <ContinueButton show={proficiency !== ""} />
      </form>
    </ScreenLayout>
  );
}

// SCREEN 5: WORKOUT DAYS

export function WorkoutDays({ workoutDays, setWorkoutDays, onContinue, onBack }) {
  const selected = Number(workoutDays);
  const valid = Number.isInteger(selected) && selected >= 1 && selected <= 7;

  return (
    <ScreenLayout
      step={5}
      title="How many days can you work out?"
      subtitle="Choose how many days per week you can dedicate to working out."
      onBack={onBack}
    >
      <form onSubmit={submitWhen(valid, onContinue)}>
        <motion.div variants={item} className="mb-5 flex items-center gap-3">
          <PixelIcon icon={ICONS.calendar} size={36} />
          <p className="text-lg">
            Days per week: <span className="text-cyan">{valid ? selected : "-"}</span>
          </p>
        </motion.div>

        <div className="grid grid-cols-7 gap-2 sm:gap-3" role="radiogroup" aria-label="Workout days per week">
          {Array.from({ length: 7 }, (_, i) => i + 1).map((n) => {
            const active = valid && n <= selected;
            return (
              <motion.button
                key={n}
                variants={item}
                type="button"
                role="radio"
                aria-checked={n === selected}
                aria-label={`${n} day${n > 1 ? "s" : ""}`}
                onClick={() => setWorkoutDays(String(n))}
                whileHover={{ y: -3 }}
                whileTap={{ scale: 0.92 }}
                className={`px-frame px-focus aspect-square text-xl font-bold transition-colors sm:text-2xl ${
                  active ? "bg-activity text-night-950" : "bg-night-900/80 text-muted hover:text-ink"
                }`}
                style={{ "--frame": active ? "#c9ffe0" : "var(--color-night-600)" }}
              >
                {n}
              </motion.button>
            );
          })}
        </div>

        <ContinueButton show={valid} />
      </form>
    </ScreenLayout>
  );
}

// SCREEN 6: WORKOUT LOCATION

const LOCATIONS = [
  { name: "Home", icon: ICONS.house, accent: "#ff5d6c" },
  { name: "Gym", icon: ICONS.dumbbell, accent: "#4d8dff" },
  { name: "Both", icon: ICONS.swap, accent: "#42e08b" },
];

export function WorkoutLocation({ workoutLocation, setWorkoutLocation, onContinue, onBack, saving, saveError }) {
  const valid = workoutLocation !== "";

  return (
    <ScreenLayout step={6} title="Where do you work out?" subtitle="Last one! Then we'll build your HealthScore." onBack={onBack}>
      <form onSubmit={submitWhen(valid && !saving, onContinue)}>
        <div className="grid grid-cols-3 gap-3 sm:gap-4">
          {LOCATIONS.map((loc) => (
            <OptionButton
              key={loc.name}
              compact
              label={loc.name}
              icon={loc.icon}
              accent={loc.accent}
              selected={workoutLocation === loc.name}
              onClick={() => setWorkoutLocation(loc.name)}
            />
          ))}
        </div>

        {saveError && (
          <p role="alert" className="mt-6 text-sm text-nutrition">
            {saveError}
          </p>
        )}

        <ContinueButton show={valid} busy={saving} label="Finish" />
      </form>
    </ScreenLayout>
  );
}
