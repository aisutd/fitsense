import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";

// SCREEN 1: NAME

function NameGreeting({ onContinue }) {
  const [name, setName] = useState("");

  function handleClick() {
    if (name.trim() === "") {
      return;
    }

    onContinue(name);
  }

  return (
    <div className="intro-screen">
      <header>
        <h1>---Welcome to FitSense---</h1>
      </header>

      <h2>Let's start with the introduction! What's your name?</h2>

      <input
        className="text-input"
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Type your name"
      />

      {name.trim() !== "" && (
        <button
          className="continue-button"
          onClick={handleClick}
        >
          Continue
        </button>
      )}
    </div>
  );
}


// SCREEN 2: INFORMATION

function Information({ name, onContinue }) {
  const [age, setAge] = useState("");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");

  function handleContinue() {
    if (
      age.trim() === "" ||
      weight.trim() === "" ||
      height.trim() === ""
    ) {
      return;
    }

    onContinue();
  }

  return (
    <div className="information-screen">
      <h1>Welcome, {name}!</h1>

      <h2>Enter Your Information</h2>

      <div className="information-inputs">
        <label>
          Age:
          <input
            className="text-input"
            type="number"
            value={age}
            onChange={(event) => setAge(event.target.value)}
            placeholder="Enter your age"
          />
        </label>

        <label>
          Weight:
          <input
            className="text-input"
            type="number"
            value={weight}
            onChange={(event) => setWeight(event.target.value)}
            placeholder="Enter your weight"
          />
        </label>

        <label>
          Height:
          <input
            className="text-input"
            type="number"
            value={height}
            onChange={(event) => setHeight(event.target.value)}
            placeholder="Enter your height"
          />
        </label>
      </div>

      <button
        className="continue-button"
        onClick={handleContinue}
        disabled={
          age.trim() === "" ||
          weight.trim() === "" ||
          height.trim() === ""
        }
      >
        Continue
      </button>
    </div>
  );
}


// SCREEN 3: FITNESS GOALS

function NextScreen({ goal, setGoal, onContinue }) {
  const goals = [
    {
      name: "Lose Weight",
      description:
        "Lose weight and improve overall health."
    },
    {
      name: "Build Muscle",
      description:
        "Build muscle and increase strength."
    },
    {
      name: "Endurance",
      description:
        "Improve endurance and cardiovascular fitness."
    },
    {
      name: "General Fitness",
      description:
        "Maintain overall fitness and well-being."
    }
  ];

  return (
    <div className="goal-screen">
      <h1>What's Your Fitness Goal?</h1>

      <div className="goal-grid">
        {goals.map((item) => (
          <div className="goal-option" key={item.name}>
            <button
              className={`goal-button ${
                goal === item.name ? "selected" : ""
              }`}
              onClick={() => setGoal(item.name)}
            >
              {goal === item.name && "✓ "}
              {item.name}
            </button>

            <p className="goal-description">
              {item.description}
            </p>
          </div>
        ))}
      </div>

      <button
        className="continue-button"
        onClick={onContinue}
        disabled={!goal}
      >
        Continue
      </button>
    </div>
  );
}


// SCREEN 4: FITNESS PROFICIENCY

function Proficiency({
  proficiency,
  setProficiency,
  onContinue
}) {
  const proficiencies = [
    {
      name: "Beginner",
      description:
        "New to fitness and looking to get started."
    },
    {
      name: "Intermediate",
      description:
        "Have some experience with fitness and looking to improve."
    },
    {
      name: "Advanced",
      description:
        "Experienced in fitness and looking for advanced challenges."
    }
  ];

  return (
    <div className="proficiency-screen">
      <h1>What's Your Fitness Proficiency?</h1>

      <div className="proficiency-list">
        {proficiencies.map((level) => (
          <div
            className="proficiency-option"
            key={level.name}
          >
            <button
              className={`proficiency-button ${
                proficiency === level.name ? "selected" : ""
              }`}
              onClick={() => setProficiency(level.name)}
            >
              {proficiency === level.name && "✓ "}
              {level.name}
            </button>

            <p className="proficiency-description">
              {level.description}
            </p>
          </div>
        ))}
      </div>

      <button
        className="continue-button"
        onClick={onContinue}
        disabled={!proficiency}
      >
        Continue
      </button>
    </div>
  );
}


// SCREEN 5: WORKOUT DAYS

function WorkoutDays({
  workoutDays,
  setWorkoutDays,
  onContinue
}) {
  const days = [
    "1 Day | ",
    "2 Days |",
    "3 Days |",
    "4 Days |",
    "5 Days |",
    "6 Days |",
    "7 Days |"
  ];

  return (
    <div className="goal-screen">
      <h1>How Many Days Can You Work Out?</h1>

      <p className="screen-description">
        Choose how many days per week you are able to dedicate
        to working out.
      </p>

      <div className="days-grid">
        {days.map((day) => (
          <button
            key={day}
            className={`goal-button ${
              workoutDays === day ? "selected" : ""
            }`}
            onClick={() => setWorkoutDays(day)}
          >
            {workoutDays === day && "✓ "}
            {day}
          </button>
        ))}
      </div>

      <button
        className="continue-button"
        onClick={onContinue}
        disabled={!workoutDays}
      >
        Continue
      </button>
    </div>
  );
}


// SCREEN 6: WORKOUT LOCATION

function WorkoutLocation({
  workoutLocation,
  setWorkoutLocation,
  onContinue
}) {
  const locations = [
    {
      name: "Gym",
      description:
        "I have access to a gym and can use gym equipment for my workouts."
    },
    {
      name: "Home",
      description:
        "I primarily work out at home with the equipment I have available."
    },
    {
      name: "Both",
      description:
        "I can work out both at a gym and at home."
    }
  ];

  return (
    <div className="proficiency-screen">
      <h1>Where Do You Work Out?</h1>

      <div className="proficiency-list">
        {locations.map((location) => (
          <div
            className="proficiency-option"
            key={location.name}
          >
            <button
              className={`proficiency-button ${
                workoutLocation === location.name
                  ? "selected"
                  : ""
              }`}
              onClick={() =>
                setWorkoutLocation(location.name)
              }
            >
              {workoutLocation === location.name && "✓ "}
              {location.name}
            </button>

            <p className="proficiency-description">
              {location.description}
            </p>
          </div>
        ))}
      </div>

      <button
        className="continue-button"
        onClick={onContinue}
        disabled={!workoutLocation}
      >
        Continue
      </button>
    </div>
  );
}


// MAIN APP

function App() {
  const [screen, setScreen] = useState(1);

  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [proficiency, setProficiency] = useState("");
  const [workoutDays, setWorkoutDays] = useState("");
  const [workoutLocation, setWorkoutLocation] = useState("");

  function handleNameContinue(nameFromScreen) {
    setName(nameFromScreen);
    setScreen(2);
  }

  function handleInformationContinue() {
    setScreen(3);
  }

  function handleGoalContinue() {
    setScreen(4);
  }

  function handleProficiencyContinue() {
    setScreen(5);
  }

  function handleWorkoutDaysContinue() {
    setScreen(6);
  }

  function handleWorkoutLocationContinue() {
    setScreen(7);
  }

  if (screen === 1) {
    return (
      <NameGreeting
        onContinue={handleNameContinue}
      />
    );
  }

  if (screen === 2) {
    return (
      <Information
        name={name}
        onContinue={handleInformationContinue}
      />
    );
  }

  if (screen === 3) {
    return (
      <NextScreen
        goal={goal}
        setGoal={setGoal}
        onContinue={handleGoalContinue}
      />
    );
  }

  if (screen === 4) {
    return (
      <Proficiency
        proficiency={proficiency}
        setProficiency={setProficiency}
        onContinue={handleProficiencyContinue}
      />
    );
  }

  if (screen === 5) {
    return (
      <WorkoutDays
        workoutDays={workoutDays}
        setWorkoutDays={setWorkoutDays}
        onContinue={handleWorkoutDaysContinue}
      />
    );
  }

  if (screen === 6) {
    return (
      <WorkoutLocation
        workoutLocation={workoutLocation}
        setWorkoutLocation={setWorkoutLocation}
        onContinue={handleWorkoutLocationContinue}
      />
    );
  }

  if (screen === 7) {
    return (
      <div className="intro-screen">
        <h1>FitSense Profile</h1>

        <p>Name: {name}</p>
        <p>Goal: {goal}</p>
        <p>Proficiency: {proficiency}</p>
        <p>Workout Days: {workoutDays}</p>
        <p>Workout Location: {workoutLocation}</p>

        <h2>Your information has been saved!</h2>
      </div>
    );
  }
}

// MOUNT TO DOM

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);