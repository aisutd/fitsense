import { motion } from "motion/react";
import PixelIcon from "./components/PixelIcon";
import { ICONS } from "./icons";

// Shared shell for the onboarding screens: logo, stage bar, title column and
// a framed panel for the inputs. Children animate in one after another; wrap
// anything that should join the stagger in <motion.div variants={item}>.

export const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 260, damping: 22 } },
};

const column = {
  hidden: {},
  show: { transition: { delayChildren: 0.25, staggerChildren: 0.08 } },
};

const panel = {
  hidden: { opacity: 0, y: 24, scale: 0.98 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 220, damping: 24, delayChildren: 0.15, staggerChildren: 0.06 },
  },
};

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <PixelIcon icon={ICONS.trophy} size={26} />
      <span className="font-title text-xl font-bold tracking-wider sm:text-2xl">FITSENSE</span>
    </div>
  );
}

function StageBar({ step, total }) {
  return (
    <div className="flex items-center gap-3" aria-label={`Step ${step} of ${total}`}>
      <span className="hidden text-sm text-muted sm:inline">STAGE {step}/{total}</span>
      <div className="flex gap-1">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-3 w-5 sm:w-7 ${
              i < step - 1 ? "bg-activity" : i === step - 1 ? "bg-cyan blink" : "bg-night-700"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

function ScreenLayout({ step, totalSteps = 6, title, subtitle, onBack, children }) {
  return (
    <main className="relative z-10 mx-auto flex min-h-screen w-full max-w-6xl flex-col px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <header className="flex items-center justify-between gap-4">
        <Logo />
        {step && <StageBar step={step} total={totalSteps} />}
      </header>

      <motion.section
        className="mt-[6vh] grid items-start gap-10 md:mt-[10vh] md:grid-cols-[1fr_1.15fr] md:gap-14"
        variants={column}
        initial="hidden"
        animate="show"
      >
        <div>
          <motion.h1 variants={item} className="text-4xl font-bold leading-tight sm:text-5xl lg:text-6xl">
            {title}
          </motion.h1>
          {subtitle && (
            <motion.p variants={item} className="mt-4 max-w-md text-lg text-muted">
              {subtitle}
            </motion.p>
          )}
          {onBack && (
            <motion.button
              variants={item}
              type="button"
              onClick={onBack}
              className="px-focus mt-8 text-muted transition-colors hover:text-ink"
            >
              ◀ Back
            </motion.button>
          )}
        </div>

        <motion.div variants={panel} className="px-frame px-glow bg-night-800/85 p-5 backdrop-blur-sm sm:p-8">
          {children}
        </motion.div>
      </motion.section>
    </main>
  );
}

export default ScreenLayout;
