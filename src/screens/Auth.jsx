import { useState } from "react";
import { motion } from "motion/react";
import ScreenLayout, { item } from "../ScreenLayout";
import ContinueButton from "../ContinueButton";
import PixelField from "../components/PixelField";
import { ICONS } from "../icons";
import { login, signup } from "../api";

// Testing login: username + password. Sign up continues into onboarding;
// log in goes to the dashboard (or onboarding if the profile isn't finished).

const USERNAME_RE = /^[A-Za-z0-9_.-]{3,30}$/;

function errorText(mode, error) {
  if (error.status === 401) return "Wrong username or password.";
  if (error.status === 409) return "That username is taken. Try another, or log in.";
  if (error.status === 422) return "Usernames are 3-30 letters, numbers, _ . or -. Passwords need 8+ characters.";
  if (error.status === 0) return error.message;
  return mode === "login" ? "Couldn't log in. Please try again." : "Couldn't create your account. Please try again.";
}

function Auth({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // login | signup
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isSignup = mode === "signup";
  const valid = isSignup ? USERNAME_RE.test(username) && password.length >= 8 : username.trim() !== "" && password !== "";

  function switchMode(next) {
    setMode(next);
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError("");
    try {
      const account = await (isSignup ? signup : login)(username.trim(), password);
      onAuthenticated(account);
    } catch (e) {
      setError(errorText(mode, e));
      setBusy(false);
    }
  }

  return (
    <ScreenLayout
      title={
        isSignup ? (
          <>
            New player?
            <br />
            <span className="text-activity">Create a save.</span>
          </>
        ) : (
          <>
            Welcome back,
            <br />
            <span className="text-activity">player.</span>
          </>
        )
      }
      subtitle={
        isSignup
          ? "Pick a username and password, then set up your profile."
          : "Log in to see your HealthScore and keep logging."
      }
    >
      <motion.div variants={item} className="mb-6 grid grid-cols-2 gap-2" role="tablist" aria-label="Log in or sign up">
        {[
          ["login", "Log in"],
          ["signup", "Sign up"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            onClick={() => switchMode(id)}
            className={`px-frame px-focus py-2 text-lg transition-colors ${
              mode === id ? "bg-night-700 text-ink [--frame:var(--color-cyan)]" : "text-muted hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </motion.div>

      <form onSubmit={handleSubmit} className="space-y-6" key={mode}>
        <PixelField
          icon={ICONS.player}
          label="Username"
          type="text"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={isSignup ? "3-30 letters or numbers" : "Your username"}
          maxLength={30}
          autoFocus
        />
        <PixelField
          icon={ICONS.star}
          label="Password"
          type="password"
          name="password"
          autoComplete={isSignup ? "new-password" : "current-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={isSignup ? "At least 8 characters" : "Your password"}
          maxLength={128}
        />

        {error && (
          <p role="alert" className="text-nutrition">
            {error}
          </p>
        )}

        <ContinueButton show={valid} busy={busy} busyLabel={isSignup ? "Creating..." : "Logging in..."} label={isSignup ? "Sign up" : "Log in"} />
      </form>
    </ScreenLayout>
  );
}

export default Auth;
