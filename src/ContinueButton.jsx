import { motion } from "motion/react";
import { item } from "./ScreenLayout";

// Submit button for an onboarding form. Stays visible but disabled until the
// screen is valid, so players can see what they're working toward.
function ContinueButton({ show, busy = false, label = "Continue" }) {
  const disabled = !show || busy;

  return (
    <motion.div variants={item} className="mt-8 flex justify-end">
      <button
        type="submit"
        disabled={disabled}
        className={`px-button px-6 py-3 text-lg font-semibold tracking-wide ${
          disabled
            ? "cursor-not-allowed bg-night-700 text-muted opacity-60"
            : "bg-activity text-night-950 hover:bg-[#6bf0a6]"
        }`}
        style={disabled ? { "--frame": "var(--color-night-500)", "--shadow": "var(--color-night-700)" } : { "--frame": "#c9ffe0", "--shadow": "#1d7a48" }}
      >
        {busy ? "Saving..." : `${label} ▶`}
      </button>
    </motion.div>
  );
}

export default ContinueButton;
