import { useMemo, useState } from "react";
import PixelIcon from "./PixelIcon";
import { ICONS } from "../icons";

// Pixelated donut chart split into four quadrants (one per HealthScore
// category). Each quadrant lights up clockwise in proportion to its score.
// Lit cells pop in along the sweep, and each quadrant gets its own glow layer.
// With onPick, each quadrant is also a button (clipped to its own arc) that
// opens quick logging for that category. Hovering, focusing or opening one
// lights its own cells (the dim track takes the category's color, the glow
// grows), so the highlight stays on the pixel grid. Each section is marked
// with its category's pixel icon: on touch screens always, with a "+" badge
// (an "x" while open); with a mouse only while lit, so the ring stays clean.

const N = 46; // grid size in cells
const C = (N - 1) / 2;
const OUTER = 22.5;
const INNER = 15.5;
const GAP = 1.1; // half-width of the empty cross between quadrants

// Clockwise from 12 o'clock: top-right, bottom-right, bottom-left, top-left.
const QUADRANT_ORDER = ["workouts", "sleep", "activity", "nutrition"];

function buildCells() {
  const cells = [];
  for (let y = 0; y < N; y += 1) {
    for (let x = 0; x < N; x += 1) {
      const dx = x - C;
      const dy = y - C;
      const dist = Math.hypot(dx, dy);
      if (dist > OUTER || dist < INNER) continue;
      if (Math.abs(dx) < GAP || Math.abs(dy) < GAP) continue;
      let angle = Math.atan2(dx, -dy); // 0 at top, clockwise
      if (angle < 0) angle += Math.PI * 2;
      const quadrant = Math.floor(angle / (Math.PI / 2));
      const progress = (angle - quadrant * (Math.PI / 2)) / (Math.PI / 2);
      // Cells near the outer edge are slightly brighter for a bevelled look.
      const edge = dist > OUTER - 1.6 ? "hi" : dist < INNER + 1.4 ? "lo" : "mid";
      cells.push({ x, y, angle, quadrant, progress, edge });
    }
  }
  return cells;
}

const CELLS = buildCells();

// A quadrant's arc as a CSS polygon, in % of the ring's box (0 degrees at 12 o'clock, clockwise).
const HIT_OUTER = 50;
const HIT_INNER = 32;
function arcPolygon(q, steps = 10) {
  const point = (deg, r) => {
    const a = (deg * Math.PI) / 180;
    return `${(50 + r * Math.sin(a)).toFixed(2)}% ${(50 - r * Math.cos(a)).toFixed(2)}%`;
  };
  const from = q * 90, outer = [], inner = [];
  for (let i = 0; i <= steps; i += 1) {
    const deg = from + (90 * i) / steps;
    outer.push(point(deg, HIT_OUTER));
    inner.unshift(point(deg, HIT_INNER));
  }
  return `polygon(${[...outer, ...inner].join(", ")})`;
}
const HIT_SHAPES = QUADRANT_ORDER.map((_, q) => arcPolygon(q));
// where each quadrant's marker sits: the middle of its arc, in the middle of the band
const MARKER_SPOTS = QUADRANT_ORDER.map((_, q) => {
  const a = ((q * 90 + 45) * Math.PI) / 180, r = (HIT_OUTER + HIT_INNER) / 2;
  return { left: `${50 + r * Math.sin(a)}%`, top: `${50 - r * Math.cos(a)}%` };
});

// A pixel icon with a 1 px dark outline, so it reads over lit and unlit cells alike.
const OUTLINE = "#0a1122";
function outlined({ art, colors }) {
  const w = Math.max(...art.map((row) => row.length)), h = art.length;
  const solid = (x, y) => y >= 0 && y < h && x >= 0 && x < w && art[y][x] && art[y][x] !== "." && colors[art[y][x]];
  const rows = [];
  for (let y = -1; y <= h; y += 1) {
    let row = "";
    for (let x = -1; x <= w; x += 1) {
      if (solid(x, y)) row += art[y][x];
      else row += solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1) ? "#" : ".";
    }
    rows.push(row);
  }
  return { colors: { ...colors, "#": OUTLINE }, art: rows };
}
const MARKER_ICONS = {
  workouts: outlined(ICONS.dumbbell),
  sleep: outlined(ICONS.moon),
  activity: outlined(ICONS.runner),
  nutrition: outlined(ICONS.apple),
};
const BADGE_COLORS = { o: OUTLINE, w: "#e8edff" };
const PLUS_BADGE = { colors: BADGE_COLORS, art: ["..ooo..", "..owo..", "ooowooo", "owwwwwo", "ooowooo", "..owo..", "..ooo.."] };
const CLOSE_BADGE = { colors: BADGE_COLORS, art: ["oo...oo", "owo.owo", ".owowo.", "..owo..", ".owowo.", "owo.owo", "oo...oo"] };
// icon width in % of the ring (one icon pixel is a quarter of a ring cell)
const MARKER_WIDTH = `${(14 / 4 / N) * 100}%`;

function ScoreRing({ scores, categories, children, className = "", onPick, picked }) {
  const [hovered, setHovered] = useState(null);
  const lit = (key) => key === hovered || key === picked;
  const layers = useMemo(() => {
    const byKey = Object.fromEntries(categories.map((c) => [c.key, c]));
    return QUADRANT_ORDER.map((key, q) => {
      const cat = byKey[key];
      const lit = (scores[key].score ?? 0) / 100;
      return {
        key,
        color: cat.color,
        shades: cat.shades,
        cells: CELLS.filter((cell) => cell.quadrant === q).map((cell) => ({
          ...cell,
          lit: cell.progress <= lit,
        })),
      };
    });
  }, [scores, categories]);

  return (
    <div className={`relative aspect-square ${className}`}>
      {/* Dim track for the unfilled part of every quadrant */}
      <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${N} ${N}`} shapeRendering="crispEdges" aria-hidden="true">
        {layers.flatMap((layer) =>
          layer.cells
            .filter((c) => !c.lit)
            .map((c) => (
              <rect
                key={`${layer.key}-${c.x}-${c.y}`}
                x={c.x}
                y={c.y}
                width={1}
                height={1}
                fill={lit(layer.key) ? layer.color : "#1f2c4f"}
                fillOpacity={lit(layer.key) ? (c.edge === "hi" ? 0.45 : 0.3) : 1}
              />
            ))
        )}
      </svg>

      {/* One glowing layer per category */}
      {layers.map((layer) => (
        <svg
          key={layer.key}
          className="absolute inset-0 h-full w-full"
          style={{ filter: lit(layer.key) ? `drop-shadow(0 0 14px ${layer.color}) brightness(1.15)` : `drop-shadow(0 0 10px ${layer.color}99)` }}
          viewBox={`0 0 ${N} ${N}`}
          shapeRendering="crispEdges"
          aria-hidden="true"
        >
          {layer.cells
            .filter((c) => c.lit)
            .map((c) => (
              <rect
                key={`${c.x}-${c.y}`}
                className="ring-cell"
                style={{ animationDelay: `${150 + (c.angle / (Math.PI * 2)) * 900}ms` }}
                x={c.x}
                y={c.y}
                width={1}
                height={1}
                fill={c.edge === "hi" ? layer.shades[1] : layer.color}
                opacity={c.edge === "lo" ? 0.7 : 1}
              />
            ))}
        </svg>
      ))}

      {/* Inner disc */}
      <div
        className="absolute rounded-full bg-night-900/90"
        style={{ inset: `${((C - INNER + 2.5) / N) * 100}%`, boxShadow: "inset 0 0 0 4px #121b34, 0 0 40px #0008" }}
      />
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">{children}</div>

      {onPick &&
        layers.map((layer, q) => {
          const cat = categories.find((c) => c.key === layer.key);
          const open = picked === layer.key;
          return (
            <button
              key={layer.key}
              type="button"
              data-quicklog={layer.key}
              aria-label={`Log ${cat.label.toLowerCase()}`}
              aria-haspopup="dialog"
              aria-expanded={open}
              onClick={(event) => onPick(open ? null : layer.key, event.currentTarget)}
              onPointerEnter={() => setHovered(layer.key)}
              onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(layer.key)}
              onBlur={() => setHovered(null)}
              className="absolute inset-0 z-10 cursor-pointer outline-none"
              style={{ clipPath: HIT_SHAPES[q] }}
            >
              <span
                aria-hidden="true"
                data-lit={lit(layer.key) || undefined}
                className="ring-marker absolute -translate-x-1/2 -translate-y-1/2"
                style={{ ...MARKER_SPOTS[q], width: MARKER_WIDTH }}
              >
                <PixelIcon icon={MARKER_ICONS[layer.key]} className="h-auto w-full" />
                <PixelIcon icon={open ? CLOSE_BADGE : PLUS_BADGE} className="ring-marker-badge absolute -bottom-[18%] -right-[22%] h-auto w-1/2" />
              </span>
            </button>
          );
        })}
    </div>
  );
}

export default ScoreRing;
