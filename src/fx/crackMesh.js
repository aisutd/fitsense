// A seamless tile of hairline cracks for the heartbeat ripple (HeartbeatBackdrop). Every crack is
// horizontal or vertical: a jittered grid of points joined by stepped lines (across, a short jog,
// across again), so the network looks irregular without any slanted lines, in keeping with the
// pixel style. Generated once from a fixed seed, so it looks the same every time. Returns a CSS url()
// for background-image, and the tile size.

function random(seed) {   // mulberry32
  let t = seed >>> 0;
  return () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

export function crackMesh({ size = 240, cells = 6, jitter = 12, seed = 7, color = "#a8f7d4", width = 1 } = {}) {
  const rand = random(seed);
  const step = size / cells;
  const wrap = (n) => ((n % cells) + cells) % cells;
  const offsets = Array.from({ length: cells }, () =>
    Array.from({ length: cells }, () => [Math.round((rand() * 2 - 1) * jitter), Math.round((rand() * 2 - 1) * jitter)]));
  const point = (i, j) => {
    const [dx, dy] = offsets[wrap(i)][wrap(j)];
    return [i * step + dx, j * step + dy];
  };

  const lines = [];
  // to the next point along a row: across, jog to its height, across (horizontal and vertical only)
  const across = (a, b) => {
    const x = Math.round(a[0] + (b[0] - a[0]) * (0.3 + rand() * 0.4));
    lines.push([a, [x, a[1]], [x, b[1]], b]);
  };
  // to the next point down a column: down, jog across, down
  const down = (a, b) => {
    const y = Math.round(a[1] + (b[1] - a[1]) * (0.3 + rand() * 0.4));
    lines.push([a, [a[0], y], [b[0], y], b]);
  };
  for (let i = 0; i < cells; i += 1) {
    for (let j = 0; j < cells; j += 1) {
      if (rand() < 0.75) across(point(i, j), point(i + 1, j));
      if (rand() < 0.75) down(point(i, j), point(i, j + 1));
    }
  }
  // each line also drawn one tile over, so lines crossing an edge continue on the next tile
  const shifts = [[0, 0], [-size, 0], [0, -size], [-size, -size]];
  const d = lines.flatMap((pts) => shifts.map(([sx, sy]) =>
    `M${pts.map(([x, y]) => `${x + sx + 0.5} ${y + sy + 0.5}`).join(" L")}`)).join(" ");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges">`
    + `<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}"/></svg>`;
  return { image: `url("data:image/svg+xml,${encodeURIComponent(svg)}")`, size };
}
