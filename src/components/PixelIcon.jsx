import { useMemo } from "react";

// Renders an icon from src/icons.js as crisp SVG pixels. Horizontal runs of
// the same colour are merged into one <rect> to keep the DOM small.
function PixelIcon({ icon, size = 32, className = "", title }) {
  const { art, colors } = icon;
  const width = Math.max(...art.map((row) => row.length));
  const height = art.length;

  const rects = useMemo(() => {
    const out = [];
    art.forEach((row, y) => {
      let x = 0;
      while (x < row.length) {
        const ch = row[x];
        if (ch === "." || !colors[ch]) {
          x += 1;
          continue;
        }
        let run = 1;
        while (row[x + run] === ch) run += 1;
        out.push({ x, y, w: run, fill: colors[ch] });
        x += run;
      }
    });
    return out;
  }, [art, colors]);

  // Size refers to the longer side so tall and wide icons line up visually.
  const scale = size / Math.max(width, height);

  return (
    <svg
      className={`shrink-0 ${className}`}
      viewBox={`0 0 ${width} ${height}`}
      width={width * scale}
      height={height * scale}
      shapeRendering="crispEdges"
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {rects.map((r, i) => (
        <rect key={i} x={r.x} y={r.y} width={r.w} height={1} fill={r.fill} />
      ))}
    </svg>
  );
}

export default PixelIcon;
