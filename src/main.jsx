import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./app.css";
import ScreenLayout from "./ScreenLayout";
import ContinueButton from "./ContinueButton";
import OptionButton from "./OptionButton";

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
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[10vw] font-light leading-none">
        FIT SENSE
      </h1>

      <div className="ml-[35vw] mt-[8vh] max-w-md px-4">
        <h2 className="text-xl md:text-2xl">
          Let's start with the introduction! What's your name?
        </h2>

        <input
          className="mt-4 w-full border-b-2 border-neutral-200 bg-transparent py-2 text-xl text-white outline-none placeholder:text-neutral-500"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Type your name"
        />

        <ContinueButton
          show={name.trim() !== ""}
          onClick={handleClick}
        />
      </div>
    </ScreenLayout>
  );
}


// SCREEN 2: INFORMATION

function Information({
  name,
  age,
  setAge,
  weight,
  setWeight,
  feet,
  setFeet,
  inches,
  setInches,
  onContinue
}) {
  const inputClass =
    "mt-2 w-full border-b-2 border-neutral-200 bg-transparent py-2 text-xl text-white outline-none placeholder:text-neutral-500";

  const canContinue =
    Number(age) > 0 && Number(weight) > 0 && Number(feet) > 0;

  return (
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        Welcome, {name}!
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-md px-4">
        <h2 className="text-xl md:text-2xl">Enter Your Information</h2>

        <label className="mt-6 block text-lg">
          Age
          <input
            className={inputClass}
            type="number"
            value={age}
            onChange={(event) => setAge(event.target.value)}
            placeholder="Enter your age"
          />
        </label>

        <label className="mt-6 block text-lg">
          Weight (lbs)
          <input
            className={inputClass}
            type="number"
            value={weight}
            onChange={(event) => setWeight(event.target.value)}
            placeholder="Enter your weight"
          />
        </label>

        <p className="mt-6 text-lg">What is your height?</p>
        <div className="flex gap-4">
          <label className="flex-1 text-lg">
            Feet
            <input
              className={inputClass}
              type="number"
              value={feet}
              onChange={(event) => setFeet(event.target.value)}
              placeholder="Feet"
            />
          </label>

          <label className="flex-1 text-lg">
            Inches
            <input
              className={inputClass}
              type="number"
              value={inches}
              onChange={(event) => setInches(event.target.value)}
              placeholder="Inches"
            />
          </label>
        </div>

        <ContinueButton show={canContinue} onClick={onContinue} />
      </div>
    </ScreenLayout>
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
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        What's Your Fitness Goal?
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-md px-4">
        {goals.map((item) => (
          <div className="mb-6 flex flex-col items-start" key={item.name}>
            <OptionButton
              label={item.name}
              selected={goal === item.name}
              onClick={() => setGoal(item.name)}
            />

            <p className="mt-2 text-sm text-neutral-300">
              {item.description}
            </p>
          </div>
        ))}

        <ContinueButton
          show={goal !== ""}
          onClick={onContinue}
        />
      </div>
    </ScreenLayout>
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
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        What's Your Fitness Proficiency?
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-md px-4">
        {proficiencies.map((level) => (
          <div className="mb-6 flex flex-col items-start" key={level.name}>
            <OptionButton
              label={level.name}
              selected={proficiency === level.name}
              onClick={() => setProficiency(level.name)}
            />

            <p className="mt-2 text-sm text-neutral-300">
              {level.description}
            </p>
          </div>
        ))}

        <ContinueButton
          show={proficiency !== ""}
          onClick={onContinue}
        />
      </div>
    </ScreenLayout>
  );
}

// SCREEN 5: WORKOUT DAYS

function WorkoutDays({
  workoutDays,
  setWorkoutDays,
  onContinue
}) {
  const daysNumber = Number(workoutDays);
  const isValid =
    workoutDays !== "" &&
    Number.isInteger(daysNumber) &&
    daysNumber >= 1 &&
    daysNumber <= 7;

  return (
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        How Many Days Can You Work Out?
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-md px-4">
        <p className="text-sm text-neutral-300">
          Choose how many days per week you are able to dedicate
          to working out.
        </p>

        <label className="mt-6 block text-lg">
          Days per week
          <input
            className="mt-2 w-full border-b-2 border-neutral-200 bg-transparent py-2 text-xl text-white outline-none placeholder:text-neutral-500"
            type="number"
            value={workoutDays}
            onChange={(event) => setWorkoutDays(event.target.value)}
            placeholder="1 - 7"
          />
        </label>

        <ContinueButton
          show={isValid}
          onClick={onContinue}
        />
      </div>
    </ScreenLayout>
  );
}


// SCREEN 6: WORKOUT LOCATION

function WorkoutLocation({
  workoutLocation,
  setWorkoutLocation,
  onContinue
}) {
  const locations = ["Home", "Gym", "Both"];

  return (
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        Where Do You Work Out?
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-md px-4">
        <div className="flex flex-wrap gap-4">
          {locations.map((location) => (
            <OptionButton
              key={location}
              label={location}
              selected={workoutLocation === location}
              onClick={() => setWorkoutLocation(location)}
            />
          ))}
        </div>

        <ContinueButton
          show={workoutLocation !== ""}
          onClick={onContinue}
        />
      </div>
    </ScreenLayout>
  );
}


// MAIN APP
function ProfileItem({ label, value }) {
  return (
    <div className="mb-5">
      <p className="text-sm text-neutral-400">{label}</p>
      <p className="text-xl">{value}</p>
    </div>
  );
}
function App() {
  const [screen, setScreen] = useState(1);

  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [proficiency, setProficiency] = useState("");
  const [workoutDays, setWorkoutDays] = useState("");
  const [workoutLocation, setWorkoutLocation] = useState("");
  const [age, setAge] = useState("");
  const [weight, setWeight] = useState("");
  const [feet, setFeet] = useState("");
  const [inches, setInches] = useState("");


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
      age={age}
      setAge={setAge}
      weight={weight}
      setWeight={setWeight}
      feet={feet}
      setFeet={setFeet}
      inches={inches}
      setInches={setInches}
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
// grab the info you need on users here
if (screen === 7) {
  const height = `${feet} ft${inches !== "" ? ` ${inches} in` : ""}`;

  return (
    <ScreenLayout>
      <h1 className="px-[3vw] pt-[2vw] text-[6vw] font-light leading-none">
        FitSense Profile
      </h1>

      <div className="ml-[35vw] mt-[4vh] max-w-3xl px-4">
        <div className="flex gap-12">
          <div className="flex-1">
          <ProfileItem label="Name" value={name} />
          <ProfileItem label="Age" value={age} />
          <ProfileItem label="Weight" value={`${weight} lbs`} />
          <ProfileItem label="Height" value={height} />
        </div>

        <div className="flex-1">
          <ProfileItem label="Goal" value={goal} />
          <ProfileItem label="Proficiency" value={proficiency} />
          <ProfileItem label="Workout Days" value={workoutDays} />
          <ProfileItem label="Workout Location" value={workoutLocation} />
          </div>
        </div>

        <h2 className="mt-6 text-xl md:text-2xl">Your profile is ready!</h2>
      </div>
    </ScreenLayout>
  );
}
}
// MOUNT TO DOM

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);