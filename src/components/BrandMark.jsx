import { useId } from "react";

// The FitSense mark: a blue F over a gold S (the app's workout blue and gold), with a heartbeat line
// running behind it, blue on the left and gold on the right. A bright pulse sweeps along the line
// and the letters glow with a heartbeat (CSS in index.css: .fs-trace, .fs-glow); both stay still
// with reduced motion. Vector, so it's crisp at any size. pulse={false} drops the heartbeat line
// (public/favicon.svg is the mark without it).

const BLUE = ["#d6e4ff", "#4d8dff", "#2a5bb8", "#1a3a7a"];   // light, base, shadow, edge
const GOLD = ["#fff1a8", "#f7b733", "#c4831a", "#7a4a06"];

// letter outlines on a 64 x 84 grid; the F's stem runs down in front of the S's top bar
const F_PATH = "M19 2 H63 L59 14 H33 V21 H55 L51 31 H33 V54 H19 Z";
const S_PATH = "M0 36 H57 L53 46 H14 V54 H57 V81 H-3 L1 71 H44 V63 H0 Z";
// one line behind the letters, a beat on each side
const PULSE = "-36,41 -25,41 -21,31 -17,52 -13,36 -10,41 67,41 72,41 76,29 80,53 84,36 87,41 97,41";

function BrandMark({ size = 32, pulse = true, animated = true, className = "", title = "FitSense" }) {
  const id = useId().replace(/:/g, "");
  const view = pulse ? "-38 0 137 84" : "-8 0 75 84";
  const [, , vw, vh] = view.split(" ").map(Number);
  const label = title ? { role: "img", "aria-label": title } : { "aria-hidden": true };
  const svg = { viewBox: view, width: "100%", height: "100%", style: { position: "absolute", inset: 0, overflow: "visible" } };
  return (
    <span className={`relative inline-block shrink-0 ${className}`} style={{ width: (size * vw) / vh, height: size }} {...label}>
      {pulse && (
        <svg {...svg} aria-hidden="true">
          <defs>
            <linearGradient id={`${id}-line`} gradientUnits="userSpaceOnUse" x1="-36" y1="0" x2="97" y2="0">
              <stop offset="0" stopColor={BLUE[1]} />
              <stop offset="0.45" stopColor={BLUE[1]} />
              <stop offset="0.55" stopColor={GOLD[1]} />
              <stop offset="1" stopColor={GOLD[1]} />
            </linearGradient>
          </defs>
          <g fill="none" stroke={`url(#${id}-line)`} strokeLinejoin="round" strokeLinecap="round">
            <polyline points={PULSE} strokeWidth="2.5" opacity="0.45" />
            {/* the bright pulse travelling along it */}
            <polyline points={PULSE} strokeWidth="3.5" pathLength="100"
                      className={animated ? "fs-trace" : undefined} strokeDasharray={animated ? "16 84" : undefined}
                      opacity={animated ? 1 : 0} />
          </g>
        </svg>
      )}
      <svg {...svg} aria-hidden="true" className={animated ? "fs-glow" : undefined}>
        <defs>
          {[["blue", BLUE], ["gold", GOLD]].map(([name, [light, base, shadow]]) => (
            <linearGradient key={name} id={`${id}-${name}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={light} />
              <stop offset="0.4" stopColor={base} />
              <stop offset="1" stopColor={shadow} />
            </linearGradient>
          ))}
        </defs>
        <path d={S_PATH} fill={`url(#${id}-gold)`} stroke={GOLD[3]} strokeWidth="2" strokeLinejoin="miter" />
        <path d={F_PATH} fill={`url(#${id}-blue)`} stroke={BLUE[3]} strokeWidth="2" strokeLinejoin="miter" />
      </svg>
    </span>
  );
}

export default BrandMark;
