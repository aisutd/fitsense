import { useId, useState } from "react";

// The FitSense mark: a blue F whose stem runs down through a green S (the app's workout blue and
// activity green), with a heartbeat line behind it, blue on the left and green on the right. The S's
// top and bottom bars pass in front of the stem and its middle splits around it, so the letters
// interlock. Each beat a bright pulse sweeps along the line, the letters glow once as it passes
// behind them, and a ring ripples out across the page from the logo (HeartbeatBackdrop; CSS in
// index.css: .fs-trace, .fs-glow, .fs-ripple); all of it stays still with reduced motion. Vector,
// so it's crisp at any size. pulse={false} drops the line (public/favicon.svg is the mark without it).

const BLUE = { light: "#d6e4ff", base: "#4d8dff", shadow: "#2a5bb8", edge: "#13306b" };
const GREEN = { light: "#c8f9dd", base: "#42e08b", shadow: "#1b7a3e", edge: "#0b4424" };

// Outlines with 45-degree cut corners, in the reference image's pixel space.
const F_PATH = "M348 15 H662 L680 33 V90 L662 108 H410 V150 H582 L600 168 V204 L582 222 H410 V548 H330 V33 Z";
// the S's top bar, its left side, and the stub of its middle left of the stem
const S_TOP = "M253 280 H574 L592 298 V332 L574 350 H305 V418 H318 V478 H253 L235 460 V298 Z";
// the rest of its middle (right of the stem), its right side and its bottom bar
const S_BOTTOM = "M422 412 H582 L600 430 V617 L582 635 H268 L250 617 V570 L268 552 H530 V478 H422 Z";
// one line behind the letters: a small bump and a big beat on each side
const PULSE = "40,390 62,390 76,342 92,398 112,398 156,228 186,486 206,390 600,390 668,390 684,365 700,395 716,395 742,226 774,500 796,392 800,390";
const EXTRUDE = 7;   // the dark depth edge, down and to the right

// One clock for every heartbeat animation (the line, the glow, the page ripple in HeartbeatBackdrop):
// each starts at the same phase of a BEAT_MS cycle, whenever it mounts, so they always beat together.
export const BEAT_MS = 1800;
export const beatDelay = () => `-${Math.round(performance.now() % BEAT_MS)}ms`;

function Letter({ d, colors, fill }) {
  return (
    <>
      <path d={d} fill={colors.edge} transform={`translate(${EXTRUDE} ${EXTRUDE})`} />
      <path d={d} fill={fill} stroke={colors.edge} strokeWidth="5" strokeLinejoin="miter" />
    </>
  );
}

function BrandMark({ size = 32, pulse = true, animated = true, className = "", title = "FitSense" }) {
  const id = useId().replace(/:/g, "");
  const [delay] = useState(beatDelay);
  const view = pulse ? "30 0 780 650" : "215 0 480 650";
  const [, , vw, vh] = view.split(" ").map(Number);
  const label = title ? { role: "img", "aria-label": title } : { "aria-hidden": true };
  const svg = { viewBox: view, width: "100%", height: "100%", style: { position: "absolute", inset: 0, overflow: "visible" } };
  const gradient = (name, c) => (
    <linearGradient id={`${id}-${name}`} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor={c.light} />
      <stop offset="0.35" stopColor={c.base} />
      <stop offset="1" stopColor={c.shadow} />
    </linearGradient>
  );
  return (
    // data-heartbeat: where HeartbeatBackdrop's ripple starts
    <span className={`relative inline-block shrink-0 ${className}`} style={{ width: (size * vw) / vh, height: size }}
          data-heartbeat={pulse && animated ? "" : undefined} {...label}>
      {pulse && (
        <svg {...svg} aria-hidden="true">
          <defs>
            <linearGradient id={`${id}-line`} gradientUnits="userSpaceOnUse" x1="40" y1="0" x2="800" y2="0">
              <stop offset="0" stopColor={BLUE.base} />
              <stop offset="0.4" stopColor={BLUE.base} />
              <stop offset="0.6" stopColor={GREEN.base} />
              <stop offset="1" stopColor={GREEN.base} />
            </linearGradient>
          </defs>
          <g fill="none" stroke={`url(#${id}-line)`} strokeLinejoin="round" strokeLinecap="round">
            <polyline points={PULSE} strokeWidth="9" opacity="0.4" />
            {/* the bright pulse travelling along it, once per beat */}
            {animated && <polyline points={PULSE} strokeWidth="13" pathLength="100" strokeDasharray="14 186" className="fs-trace" style={{ animationDelay: delay }} />}
          </g>
        </svg>
      )}
      <svg {...svg} aria-hidden="true" className={animated ? "fs-glow" : undefined}
           style={{ ...svg.style, animationDelay: animated ? delay : undefined }}>
        <defs>
          {gradient("blue", BLUE)}
          {gradient("green", GREEN)}
        </defs>
        <Letter d={F_PATH} colors={BLUE} fill={`url(#${id}-blue)`} />
        <Letter d={S_TOP} colors={GREEN} fill={`url(#${id}-green)`} />
        <Letter d={S_BOTTOM} colors={GREEN} fill={`url(#${id}-green)`} />
      </svg>
    </span>
  );
}

export default BrandMark;
