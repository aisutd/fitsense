import { motion } from "motion/react";
import PixelIcon from "./PixelIcon";
import { item } from "../ScreenLayout";

// Labelled text/number input with a pixel icon and optional unit suffix.
function PixelField({ icon, label, suffix, className = "", ...inputProps }) {
  return (
    <motion.label variants={item} className={`block ${className}`}>
      <span className="mb-2 flex items-center gap-2 text-sm uppercase tracking-wider text-muted">
        {icon && <PixelIcon icon={icon} size={18} />}
        {label}
      </span>
      <span className="px-frame flex items-center gap-3 bg-night-900/80 px-3 py-2 focus-within:[--frame:var(--color-cyan)]">
        <input
          className="w-full min-w-0 bg-transparent py-1 text-xl text-ink outline-none placeholder:text-night-500"
          {...inputProps}
        />
        {suffix && <span className="shrink-0 text-muted">{suffix}</span>}
      </span>
    </motion.label>
  );
}

export default PixelField;
