import { useMemo, useState } from "react";
import { motion } from "motion/react";
import CountUp from "../components/reactbits/CountUp";
import PixelCard from "../components/reactbits/PixelCard";
import PixelIcon from "../components/PixelIcon";
import ScoreRing from "../components/ScoreRing";
import { Logo } from "../ScreenLayout";
import { ICONS, levelIcon } from "../icons";
import { CATEGORIES, RANGES, getHealthScore, scoreLabel } from "../data/healthScore";

const CATEGORY_ICONS = {
  nutrition: ICONS.apple,
  workouts: ICONS.dumbbell,
  activity: ICONS.runner,
  sleep: ICONS.moon,
};

const GOAL_ICONS = {
  "Lose Weight": ICONS.flame,
  "Build Muscle": ICONS.dumbbell,
  Endurance: ICONS.heart,
  "General Fitness": ICONS.star,
};
const LEVEL_BARS = { Beginner: 1, Intermediate: 2, Advanced: 3 };
const LOCATION_ICONS = { Home: ICONS.house, Gym: ICONS.dumbbell, Both: ICONS.swap };

const rise = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
  transition: { type: "spring", stiffness: 200, damping: 22, delay },
});

function RangeSelect({ value, onChange }) {
  return (
    <label className="px-frame flex items-center gap-3 bg-night-800/85 px-4 py-2 focus-within:[--frame:var(--color-cyan)]">
      <PixelIcon icon={ICONS.calendar} size={22} />
      <span className="sr-only">Time range</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="cursor-pointer bg-transparent pr-1 text-lg text-ink outline-none"
      >
        {RANGES.map((r) => (
          <option key={r.id} value={r.id} className="bg-night-900">
            {r.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// Category card. `side` decides which edge the connector line to the ring
// comes out of on large screens.
function CategoryCard({ category, data, side, delay }) {
  return (
    <motion.div {...rise(delay)} className="relative">
      <PixelCard
        className="hs-card px-frame px-glow"
        style={{ "--frame": category.color }}
        colors={category.shades}
        glowColor={category.color}
        gap={7}
        speed={30}
        radius={0}
        introDelay={delay * 1000 + 300}
      >
        <div className="w-full p-5 sm:p-6">
          <div className="flex items-center gap-3">
            <PixelIcon icon={CATEGORY_ICONS[category.key]} size={36} />
            <h3 className="text-2xl font-bold" style={{ color: category.color }}>
              {category.label}
            </h3>
          </div>
          <p className="mt-3 text-4xl font-bold">
            <CountUp to={data.score} duration={1.2} delay={delay + 0.3} />
            <span className="ml-1 text-xl text-muted">/100</span>
          </p>
          <p className="mt-2 text-muted">{data.note}</p>
        </div>
      </PixelCard>

      {/* Connector to the ring (desktop layout only) */}
      <div
        aria-hidden="true"
        className={`absolute top-1/2 hidden h-[3px] w-12 lg:block ${side === "left" ? "-right-14" : "-left-14"}`}
        style={{ background: category.color, boxShadow: `0 0 10px ${category.color}` }}
      >
        <span
          className={`absolute -top-[5px] h-[13px] w-[13px] border-[3px] bg-night-900 ${side === "left" ? "-right-2" : "-left-2"}`}
          style={{ borderColor: category.color }}
        />
      </div>
    </motion.div>
  );
}

function SummaryBar({ scores }) {
  return (
    <motion.div {...rise(0.7)} className="px-frame mt-14 grid grid-cols-2 bg-night-800/85 sm:grid-cols-4">
      {CATEGORIES.map((c, i) => (
        <div
          key={c.key}
          className={`flex items-center justify-center gap-4 px-4 py-5 ${i > 0 ? "sm:border-l-[3px] sm:border-night-700" : ""} ${
            i % 2 === 1 ? "border-l-[3px] border-night-700" : ""
          } ${i > 1 ? "border-t-[3px] border-night-700 sm:border-t-0" : ""}`}
        >
          <PixelIcon icon={CATEGORY_ICONS[c.key]} size={34} />
          <div>
            <p className="text-sm" style={{ color: c.color }}>
              {c.label}
            </p>
            <p className="text-2xl font-bold">
              <CountUp to={scores[c.key].score} duration={1} delay={0.9} />
              <span className="text-base text-muted">/100</span>
            </p>
          </div>
        </div>
      ))}
    </motion.div>
  );
}

function ProfileItem({ icon, label, value }) {
  return (
    <div className="flex items-center gap-3">
      <PixelIcon icon={icon} size={28} />
      <div>
        <p className="text-sm text-muted">{label}</p>
        <p className="text-lg">{value || "-"}</p>
      </div>
    </div>
  );
}

function PlayerProfile({ profile, onEdit }) {
  const height = `${profile.feet} ft${profile.inches !== "" ? ` ${profile.inches} in` : ""}`;
  const items = [
    { icon: ICONS.player, label: "Name", value: profile.name },
    { icon: ICONS.hourglass, label: "Age", value: profile.age },
    { icon: ICONS.kettlebell, label: "Weight", value: profile.weight && `${profile.weight} lbs` },
    { icon: ICONS.ruler, label: "Height", value: height },
    { icon: GOAL_ICONS[profile.goal] ?? ICONS.star, label: "Goal", value: profile.goal },
    { icon: levelIcon(LEVEL_BARS[profile.proficiency] ?? 1), label: "Proficiency", value: profile.proficiency },
    { icon: ICONS.calendar, label: "Workout Days", value: profile.workoutDays && `${profile.workoutDays} / week` },
    { icon: LOCATION_ICONS[profile.workoutLocation] ?? ICONS.house, label: "Workout Location", value: profile.workoutLocation },
  ];

  return (
    <motion.section
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.3 }}
      transition={{ type: "spring", stiffness: 160, damping: 22 }}
      className="px-frame mt-20 bg-night-800/85 p-6 sm:p-8"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-bold">Player Profile</h2>
        <button type="button" onClick={onEdit} className="px-focus text-muted transition-colors hover:text-cyan">
          ✎ Edit profile
        </button>
      </div>
      <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <ProfileItem key={it.label} {...it} />
        ))}
      </div>
    </motion.section>
  );
}

function HealthScore({ profile, onEditProfile }) {
  const [range, setRange] = useState("week");
  const { overall, scores } = useMemo(() => getHealthScore(range, profile), [range, profile]);
  const byKey = Object.fromEntries(CATEGORIES.map((c) => [c.key, c]));

  return (
    <main className="relative z-10 mx-auto w-full max-w-6xl px-4 pb-24 pt-6 sm:px-8 sm:pt-10">
      <header className="flex items-center justify-between gap-4">
        <Logo />
      </header>

      <div className="mt-10 flex flex-wrap items-end justify-between gap-6">
        <motion.div {...rise(0.1)}>
          <h1 className="text-5xl font-bold sm:text-6xl">HealthScore</h1>
          <p className="mt-3 text-lg text-muted">
            Your overall wellness at a glance{profile.name ? `, ${profile.name}` : ""}.
          </p>
        </motion.div>
        <motion.div {...rise(0.2)}>
          <RangeSelect value={range} onChange={setRange} />
        </motion.div>
      </div>

      <div className="mt-12 grid items-center gap-8 lg:grid-cols-[1fr_minmax(300px,420px)_1fr] lg:gap-x-16 lg:gap-y-0">
        <div className="grid gap-8 sm:grid-cols-2 lg:order-1 lg:grid-cols-1 lg:gap-24">
          <CategoryCard category={byKey.nutrition} data={scores.nutrition} side="left" delay={0.35} />
          <CategoryCard category={byKey.activity} data={scores.activity} side="left" delay={0.55} />
        </div>

        <motion.div
          className="order-first mx-auto w-full max-w-[420px] lg:order-2"
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: "spring", stiffness: 160, damping: 18, delay: 0.15 }}
        >
          <ScoreRing key={range} scores={scores} categories={CATEGORIES}>
            <div className="flex flex-col items-center text-center">
              <PixelIcon icon={ICONS.trophy} size={48} className="h-auto w-8 drop-shadow-[0_0_12px_#f7b73380] sm:w-12" />
              <p className="mt-1 text-5xl font-bold leading-none sm:mt-2 sm:text-7xl">
                <CountUp to={overall} duration={1.4} delay={0.4} />
              </p>
              <p className="text-base text-muted sm:text-xl">/100</p>
              <p className="text-base sm:mt-1 sm:text-xl">HealthScore</p>
              <div className="my-2 flex w-20 items-center gap-2 sm:my-3 sm:w-28" aria-hidden="true">
                <span className="h-[2px] flex-1 bg-night-500" />
                <span className="h-[6px] w-[6px] bg-cyan" />
                <span className="h-[2px] flex-1 bg-night-500" />
              </div>
              <p className="text-sm font-semibold text-activity sm:text-lg">{scoreLabel(overall)}</p>
            </div>
          </ScoreRing>
        </motion.div>

        <div className="grid gap-8 sm:grid-cols-2 lg:order-3 lg:grid-cols-1 lg:gap-24">
          <CategoryCard category={byKey.workouts} data={scores.workouts} side="right" delay={0.45} />
          <CategoryCard category={byKey.sleep} data={scores.sleep} side="right" delay={0.65} />
        </div>
      </div>

      <SummaryBar scores={scores} />
      <PlayerProfile profile={profile} onEdit={onEditProfile} />
    </main>
  );
}

export default HealthScore;
