import { memo, useMemo } from "react";

// Night-time pixel landscape: stars, drifting clouds, mountains and a pine
// forest. Drawn in a small 320x180 "pixel" coordinate space and scaled up
// with crispEdges so every shape stays blocky.

const W = 320;
const H = 180;

// Small seeded RNG so the scene is identical on every render.
function rng(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Stepped ridge line as a list of columns [x, top].
function ridge(rand, { base, amp, step }) {
  const cols = [];
  let h = base;
  for (let x = 0; x < W; x += step) {
    h += (rand() - 0.5) * amp;
    h = Math.max(base - amp * 2, Math.min(base + amp, h));
    cols.push([x, Math.round(h)]);
  }
  return cols;
}

// Pixel cloud built from stacked rows of rects.
function Cloud({ x, y, scale = 1, fill }) {
  const rows = [
    [3, 0, 4],
    [1, 1, 9],
    [0, 2, 12],
    [2, 3, 8],
  ];
  return (
    <g fill={fill}>
      {rows.map(([dx, dy, w], i) => (
        <rect key={i} x={x + dx * scale} y={y + dy * scale} width={w * scale} height={scale} />
      ))}
    </g>
  );
}

// Pine tree: stepped triangle on a trunk. `h` is the canopy height in pixels.
function pine(x, baseY, h, fill) {
  const rects = [];
  for (let i = 0; i < h; i += 1) {
    const half = Math.floor((i + 2) / 2);
    rects.push(<rect key={`${x}-${i}`} x={x - half} y={baseY - h + i} width={half * 2 + 1} height={1} fill={fill} />);
  }
  rects.push(<rect key={`${x}-t`} x={x} y={baseY} width={1} height={3} fill={fill} />);
  return rects;
}

function PixelBackground() {
  const scene = useMemo(() => {
    const rand = rng(7);

    const stars = Array.from({ length: 70 }, () => ({
      x: Math.floor(rand() * W),
      y: Math.floor(rand() * 95),
      big: rand() > 0.88,
      twinkle: rand() > 0.55,
      delay: (rand() * 3).toFixed(2),
    }));

    const far = ridge(rand, { base: 112, amp: 9, step: 6 });
    const near = ridge(rand, { base: 132, amp: 7, step: 4 });

    const backTrees = [];
    for (let x = 2; x < W; x += 5 + Math.floor(rand() * 4)) {
      backTrees.push(...pine(x, 150 + Math.floor(rand() * 4), 12 + Math.floor(rand() * 10), "#0d1528"));
    }
    const frontTrees = [];
    for (let x = 0; x < W; x += 7 + Math.floor(rand() * 6)) {
      frontTrees.push(...pine(x, 170 + Math.floor(rand() * 4), 18 + Math.floor(rand() * 14), "#080e1c"));
    }

    return { stars, far, near, backTrees, frontTrees };
  }, []);

  const ridgePath = (cols, step) =>
    `M0 ${H} ` + cols.map(([x, top]) => `L${x} ${top} L${x + step} ${top}`).join(" ") + ` L${W} ${H} Z`;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 overflow-hidden"
      style={{ background: "linear-gradient(180deg, #070c1a 0%, #0b1328 55%, #111b36 100%)" }}
    >
      <svg
        className="h-full w-full"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMax slice"
        shapeRendering="crispEdges"
      >
        {scene.stars.map((s, i) => (
          <rect
            key={i}
            className={s.twinkle ? "star-twinkle" : undefined}
            style={s.twinkle ? { animationDelay: `${s.delay}s` } : undefined}
            x={s.x}
            y={s.y}
            width={s.big ? 2 : 1}
            height={s.big ? 2 : 1}
            fill={s.big ? "#c9d6ff" : "#6f7fae"}
          />
        ))}

        <g className="cloud-drift">
          <Cloud x={18} y={34} scale={3} fill="#141e3a" />
          <Cloud x={210} y={22} scale={3} fill="#141e3a" />
          <Cloud x={130} y={62} scale={2} fill="#121a33" />
        </g>
        <g className="cloud-drift" style={{ animationDuration: "34s", animationDelay: "-12s" }}>
          <Cloud x={270} y={70} scale={2} fill="#121a33" />
          <Cloud x={60} y={80} scale={2} fill="#101830" />
        </g>

        <path d={ridgePath(scene.far, 6)} fill="#121b34" />
        <path d={ridgePath(scene.near, 4)} fill="#0f172d" />
        {scene.backTrees}
        <rect x={0} y={160} width={W} height={20} fill="#080e1c" />
        {scene.frontTrees}
      </svg>
    </div>
  );
}

export default memo(PixelBackground);
