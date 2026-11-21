// Lighter / darker versions of a hex colour, e.g. for a PixelCard's sparkle shades.

// amount > 0 mixes toward white, < 0 toward black (-1..1)
export function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  return `#${[n >> 16, (n >> 8) & 255, n & 255]
    .map((c) => Math.round(amount > 0 ? c + (255 - c) * amount : c * (1 + amount)))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
}

// light, mid and full: the three shades a PixelCard twinkles through
export function tints(hex) {
  return [shade(hex, 0.7), shade(hex, 0.35), hex];
}
