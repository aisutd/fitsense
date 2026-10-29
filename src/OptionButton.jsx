import { motion } from "motion/react";
import PixelIcon from "./components/PixelIcon";
import { item } from "./ScreenLayout";

// Selectable choice card with a pixel icon. `accent` is the frame/tint colour
// used when selected.
function OptionButton({ label, description, icon, selected, onClick, accent = "#42e08b", compact = false }) {
  return (
    <motion.button
      variants={item}
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      whileHover={{ y: -3 }}
      whileTap={{ y: 1, scale: 0.98 }}
      className={`px-frame px-focus flex w-full items-center gap-4 text-left transition-colors ${
        compact ? "flex-col justify-center gap-3 px-3 py-5 text-center" : "px-4 py-4"
      } ${selected ? "px-glow" : "hover:bg-night-700/60"}`}
      style={{
        "--frame": selected ? accent : "var(--color-night-600)",
        background: selected ? `color-mix(in srgb, ${accent} 16%, var(--color-night-800))` : undefined,
      }}
    >
      {icon && <PixelIcon icon={icon} size={compact ? 40 : 34} />}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-lg font-semibold" style={{ justifyContent: compact ? "center" : undefined }}>
          {label}
          {selected && <span style={{ color: accent }}>✔</span>}
        </span>
        {description && <span className="mt-1 block text-sm leading-snug text-muted">{description}</span>}
      </span>
    </motion.button>
  );
}

export default OptionButton;
