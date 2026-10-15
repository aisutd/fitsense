import { useEffect, useMemo } from "react";

// Full-screen pixel dissolve between screens, like an old console game.
// phase "covering": blocks pop in diagonally until the screen is hidden, then
// onCovered() fires (swap the screen there). phase "revealing": blocks pop out
// and onRevealed() fires. Each block is a plain div with a CSS animation, so a
// few hundred of them stay cheap.

const CELL = 72; // px per block
const SPREAD = 420; // ms between first and last block
const CELL_MS = 220; // keep in sync with .px-cell animation-duration

const ACCENTS = ["#ff5d6c", "#4d8dff", "#42e08b", "#a66bff", "#4fd8ff"];

function PixelTransition({ phase, onCovered, onRevealed }) {
  const active = phase !== "idle";

  // Measured when a transition starts (not on mount) so it always fits the
  // current window size; the same grid is reused for cover and reveal.
  const grid = useMemo(() => {
    if (!active) return [];
    const cols = Math.ceil(window.innerWidth / CELL);
    const rows = Math.ceil(window.innerHeight / CELL);
    const cells = [];
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const seed = Math.sin((r * cols + c + 1) * 91.7) * 43758.5453;
        const noise = seed - Math.floor(seed);
        const diagonal = (c / Math.max(1, cols - 1) + r / Math.max(1, rows - 1)) / 2;
        cells.push({
          key: `${r}-${c}`,
          left: c * CELL,
          top: r * CELL,
          order: diagonal * 0.75 + noise * 0.25,
          color: noise > 0.93 ? ACCENTS[Math.floor(noise * 1000) % ACCENTS.length] : noise > 0.5 ? "#0a1122" : "#10192f",
        });
      }
    }
    return cells;
  }, [active]);

  useEffect(() => {
    if (phase === "idle") return undefined;
    const done = phase === "covering" ? onCovered : onRevealed;
    const id = window.setTimeout(done, SPREAD + CELL_MS + 40);
    return () => window.clearTimeout(id);
  }, [phase, onCovered, onRevealed]);

  if (!active) return null;

  return (
    <div className="pointer-events-auto fixed inset-0 z-50 overflow-hidden" aria-hidden="true">
      {grid.map((cell) => (
        <div
          key={cell.key}
          className="px-cell"
          data-phase={phase}
          style={{
            left: cell.left,
            top: cell.top,
            width: CELL,
            height: CELL,
            background: cell.color,
            // Reveal runs the sweep in the same direction so it reads as a wipe.
            animationDelay: `${cell.order * SPREAD}ms`,
          }}
        />
      ))}
    </div>
  );
}

export default PixelTransition;
