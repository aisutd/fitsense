import { useMemo } from "react";

// Pixelated donut chart split into four quadrants (one per HealthScore
// category). Each quadrant lights up clockwise in proportion to its score.
// Lit cells pop in along the sweep, and each quadrant gets its own glow layer.

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

function ScoreRing({ scores, categories, children, className = "" }) {
  const layers = useMemo(() => {
    const byKey = Object.fromEntries(categories.map((c) => [c.key, c]));
    return QUADRANT_ORDER.map((key, q) => {
      const cat = byKey[key];
      const lit = scores[key].score / 100;
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
            .map((c) => <rect key={`${layer.key}-${c.x}-${c.y}`} x={c.x} y={c.y} width={1} height={1} fill="#1f2c4f" />)
        )}
      </svg>

      {/* One glowing layer per category */}
      {layers.map((layer) => (
        <svg
          key={layer.key}
          className="absolute inset-0 h-full w-full"
          style={{ filter: `drop-shadow(0 0 10px ${layer.color}99)` }}
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
      <div className="absolute inset-0 flex items-center justify-center">{children}</div>
    </div>
  );
}

export default ScoreRing;
