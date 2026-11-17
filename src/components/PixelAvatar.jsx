import { leagueStyle } from "../game/leagues";

// Pixel-art player: the fitness level sets the build, the league colours the clothes and
// unlocks accessories (they stack), the body is the player's pick (male / female), and the outfit
// from the FitCoin shop (skin) adds a themed hood and extras on top.
// Drawn on a 32 x 45 grid as SVG rects so it stays crisp at any size.
const W = 32;
const H = 45;
const OY = 4; // room above the head for the crown and horns

const BUILDS = {
  male: {
    beginner: { tw: 10, aw: 2, lw: 3, sleeve: 5, bulge: 0, bulgeY: 0 },
    intermediate: { tw: 12, aw: 3, lw: 3, sleeve: 3, bulge: 2, bulgeY: 16 },
    advanced: { tw: 14, aw: 4, lw: 4, sleeve: 0, bulge: 4, bulgeY: 15 },
  },
  female: {
    beginner: { tw: 10, aw: 2, lw: 3, sleeve: 5, bulge: 0, bulgeY: 0 },
    intermediate: { tw: 10, aw: 3, lw: 3, sleeve: 3, bulge: 1, bulgeY: 16 },
    advanced: { tw: 12, aw: 3, lw: 4, sleeve: 0, bulge: 3, bulgeY: 15 },
  },
};

const SKIN = "#f0b98a";
const SKIN_D = "#c98a5c";
const INK = "#0a1122";
const GOLD = "#ffd23f";

// Shop outfits: colours, and what each adds behind the body (back) and over the head (head).
export const SKINS = {
  starter: null,
  fox: {
    color: "#ff8a3d", deep: "#b4521c", light: "#ffe2c8",
    back: (R, f) => { R(f.tailX, 27, 3, 2, "#ff8a3d"); R(f.tailX + 2, 24, 2, 4, "#ff8a3d"); R(f.tailX + 2, 22, 2, 2, "#ffe2c8"); },
    head: (R) => {
      R(11, -1, 2, 2, "#ff8a3d"); R(11, -2, 1, 1, "#ff8a3d"); R(12, 0, 1, 1, "#ffe2c8");     // ears
      R(19, -1, 2, 2, "#ff8a3d"); R(20, -2, 1, 1, "#ff8a3d"); R(19, 0, 1, 1, "#ffe2c8");
      R(12, 4, 8, 1, "#ffe2c8");                                                          // white trim
    },
  },
  owl: {
    color: "#8a5a32", deep: "#5c3a1e", light: "#e8c89a",
    back: (R, f) => { R(f.xl - 2, 15, 2, 9, "#5c3a1e"); R(f.xr + f.aw, 15, 2, 9, "#5c3a1e"); },  // folded wings
    head: (R) => {
      R(10, -1, 2, 2, "#8a5a32"); R(10, -2, 1, 1, "#e8c89a");                              // ear tufts
      R(20, -1, 2, 2, "#8a5a32"); R(21, -2, 1, 1, "#e8c89a");
      R(12, 7, 3, 3, "#f7b733"); R(17, 7, 3, 3, "#f7b733");                               // round eyes,
      R(13, 8, 1, 1, INK); R(18, 8, 1, 1, INK); R(12, 7, 1, 1, "#fff1c4"); R(17, 7, 1, 1, "#fff1c4"); // apart
      R(15, 9, 2, 1, "#f7b733"); R(15, 10, 2, 1, "#c4831a");                              // beak
    },
  },
  tiger: {
    color: "#ff9a1f", deep: "#b86200", light: "#fff1dd",
    back: (R, f) => { R(f.tailX, 28, 4, 1, "#ff9a1f"); R(f.tailX + 1, 28, 1, 1, INK); R(f.tailX + 3, 26, 1, 3, "#ff9a1f"); },
    head: (R) => {
      R(11, -1, 3, 2, "#ff9a1f"); R(12, 0, 1, 1, "#ff8fa3");                              // round ears, pink inside
      R(18, -1, 3, 2, "#ff9a1f"); R(19, 0, 1, 1, "#ff8fa3");
      R(12, 2, 2, 1, INK); R(18, 2, 2, 1, INK); R(15, 1, 2, 1, INK); R(15, 3, 2, 1, INK); // stripes
      R(11, 6, 1, 2, INK); R(20, 6, 1, 2, INK); R(12, 4, 8, 1, "#fff1dd");                // cheek stripes, trim
    },
  },
  dragon: {
    color: "#2fd07a", deep: "#138a4c", light: "#c8ffe0",
    back: (R) => {   // wings rising behind the shoulders (inside the banner's head-and-shoulders crop)
      for (const side of [-1, 1]) {
        const at = (dx, y, w, h, c) => R(side < 0 ? 10 - dx - w + 1 : 21 + dx, y, w, h, c);
        at(1, 4, 2, 2, "#2fd07a");                                                    // wing tip
        at(0, 6, 4, 4, "#138a4c"); at(0, 10, 3, 3, "#138a4c"); at(0, 13, 2, 2, "#138a4c");  // membrane
        at(3, 5, 1, 5, "#2fd07a");                                                    // outer edge
      }
    },
    head: (R) => {
      R(12, -1, 2, 2, "#fff1c4"); R(11, -3, 2, 2, "#fff1c4"); R(10, -4, 1, 1, "#fff1c4");  // horns, curving out
      R(18, -1, 2, 2, "#fff1c4"); R(19, -3, 2, 2, "#fff1c4"); R(21, -4, 1, 1, "#fff1c4");
      R(15, 0, 2, 1, "#c8ffe0"); R(14, 4, 1, 1, "#c8ffe0"); R(17, 4, 1, 1, "#c8ffe0");     // ridge, scales
    },
  },
};

export function avatarRects({ tier = 0, level = "beginner", body = "male", skin = "starter" }) {
  const female = body === "female";
  const lvl = String(level || "").toLowerCase();
  const b = BUILDS[female ? "female" : "male"][lvl] || BUILDS.male.beginner;
  const adv = lvl === "advanced";
  const t = Math.max(0, Math.min(8, Number(tier) || 0));
  const L = leagueStyle(t);
  const HAIR = female ? "#5a2a14" : "#3b2416";
  const rects = [];
  const R = (x, y, w, h, c) => rects.push([x, y + OY, w, h, c]);

  const cx = 16;
  const x0 = cx - b.tw / 2;
  const x1 = x0 + b.tw;
  const xl = x0 - b.aw;
  const xr = x1;
  const hipW = adv && !female ? b.tw - 2 : b.tw;
  const hx = cx - hipW / 2;

  R(9, 40, 14, 1, "rgba(0,0,0,0.45)"); // ground shadow

  if (t >= 6) { // Ruby+: cape behind the body
    R(xl - 1, 13, b.tw + 2 * b.aw + 2, 23, L.deep);
    R(xl - 1, 13, b.tw + 2 * b.aw + 2, 1, L.color);
    R(xl - 1, 35, b.tw + 2 * b.aw + 2, 1, L.color);
  }
  if (female) { R(21, 4, 2, 2, HAIR); R(22, 6, 2, 7, HAIR); R(22, 12, 1, 2, HAIR); } // ponytail
  const outfit = SKINS[skin] || null;
  const frame = { xl, xr, aw: b.aw, tailX: hx + hipW };
  if (outfit) outfit.back(R, frame);

  // head
  R(12, 4, 8, 8, SKIN); R(19, 5, 1, 6, SKIN_D);
  R(11, 8, 1, 2, SKIN); R(20, 8, 1, 2, SKIN);
  R(11, 2, 10, 3, HAIR);
  R(14, 8, 1, 1, INK); R(17, 8, 1, 1, INK);
  if (female) {
    R(11, 5, 1, 5, HAIR); R(20, 5, 1, 5, HAIR); R(12, 4, 3, 1, HAIR);
    R(13, 7, 2, 1, INK); R(17, 7, 2, 1, INK);
    R(15, 10, 2, 1, "#d9687a");
    R(14, 12, 4, 1, SKIN_D);
  } else {
    R(11, 5, 1, 3, HAIR); R(20, 5, 1, 3, HAIR);
    R(15, 10, 2, 1, SKIN_D);
    if (adv) R(13, 12, 6, 1, SKIN_D); else R(14, 12, 4, 1, SKIN_D);
  }

  if (outfit) { // the outfit's hood over the hair, then its ears / horns / goggles
    R(11, 1, 10, 4, outfit.color); R(11, 5, 1, 5, outfit.color); R(20, 5, 1, 5, outfit.color);
    R(20, 2, 1, 3, outfit.deep);
    outfit.head(R);
  }

  // torso: shirt in the league colour
  if (adv) {
    R(x0, 13, b.tw, 5, L.color); R(x0 + 1, 18, b.tw - 2, 7, L.color);
    R(x1 - 2, 18, 1, 7, L.deep); R(x1 - 1, 13, 1, 5, L.deep);
    R(x0, 13, 2, 2, SKIN); R(x1 - 2, 13, 2, 2, SKIN); // tank-top shoulders
    if (female) R(x0, 22, b.tw, 3, L.color);
    else R(cx - 4, 17, 8, 1, L.deep);
  } else {
    R(x0, 13, b.tw, 12, L.color); R(x1 - 1, 13, 1, 12, L.deep);
  }
  R(15, 13, 2, 2, SKIN);
  if (t < 4) R(x0 + 2, 15, 2, 2, L.light); // league crest

  // arms
  R(xl, 13, b.aw, 12, SKIN); R(xr, 13, b.aw, 12, SKIN); R(xl, 13, 1, 12, SKIN_D);
  if (b.bulge) { R(xl - 1, b.bulgeY, 1, b.bulge, SKIN); R(xr + b.aw, b.bulgeY, 1, b.bulge, SKIN_D); }
  if (adv) { R(xl - 1, 21, 1, 2, SKIN); R(xr + b.aw, 21, 1, 2, SKIN_D); }
  if (b.sleeve) { R(xl, 13, b.aw, b.sleeve, L.color); R(xr, 13, b.aw, b.sleeve, L.color); R(xr + b.aw - 1, 13, 1, b.sleeve, L.deep); }
  R(xl, 25, b.aw, 2, SKIN); R(xr, 25, b.aw, 2, SKIN);

  // shorts, legs, socks, shoes
  R(hx, 25, hipW, 5, L.deep); R(hx, 25, 1, 5, L.color); R(hx + hipW - 1, 25, 1, 5, L.color);
  const lx = cx - 1 - b.lw;
  const rx = cx + 1;
  R(lx, 30, b.lw, 8, SKIN); R(rx, 30, b.lw, 8, SKIN); R(rx + b.lw - 1, 30, 1, 6, SKIN_D);
  if (adv) { R(lx - 1, 32, 1, 3, SKIN); R(rx + b.lw, 32, 1, 3, SKIN_D); }
  R(lx, 36, b.lw, 2, "#f4f6ff"); R(rx, 36, b.lw, 2, "#f4f6ff");
  R(lx - 1, 38, b.lw + 1, 2, L.light); R(rx, 38, b.lw + 1, 2, L.light);
  R(lx - 1, 39, b.lw + 1, 1, INK); R(rx, 39, b.lw + 1, 1, INK);
  if (t >= 2) { R(lx, 38, 1, 1, L.color); R(rx + b.lw - 1, 38, 1, 1, L.color); }

  // accessories, one more per league
  R(xl, 23, b.aw, 1, L.light); // Bronze: wristband
  if (t >= 1) { // headband
    R(12, 6, 8, 1, L.color);
    if (female) R(21, 5, 2, 1, L.color); else { R(20, 6, 2, 1, L.color); R(21, 7, 1, 2, L.color); }
  }
  if (t >= 2) { R(xr - 1, 13, 2, 6, "#f4f6ff"); R(xr - 1, 19, 2, 1, "#c9d2ee"); } // towel
  if (t >= 3) { // gloves + second band
    R(xr, 23, b.aw, 1, L.light);
    R(xl, 25, b.aw, 2, "#1c2236"); R(xr, 25, b.aw, 2, "#1c2236");
    R(xl, 25, b.aw, 1, L.color); R(xr, 25, b.aw, 1, L.color);
  }
  if (t >= 4) { R(14, 13, 1, 4, "#ff4d6d"); R(17, 13, 1, 4, "#4d8dff"); R(14, 17, 4, 3, GOLD); R(15, 18, 2, 1, "#b8860b"); } // medal
  if (t >= 5) { R(hx, 24, hipW, 2, "#3a2414"); R(cx - 1, 24, 2, 2, L.light); } // lifting belt
  if (t >= 6) { R(x0, 13, 1, 1, GOLD); R(x1 - 1, 13, 1, 1, GOLD); } // cape clasps
  if (t >= 7) { R(13, 8, 3, 2, INK); R(16, 8, 3, 2, INK); R(13, 8, 1, 1, L.light); R(16, 8, 1, 1, L.light); } // shades
  if (t >= 8) { // crown
    R(12, -1, 8, 2, GOLD); R(12, -2, 1, 1, GOLD); R(15, -2, 2, 1, GOLD); R(19, -2, 1, 1, GOLD);
    R(15, -1, 2, 1, "#4d6bff");
  }
  return rects;
}

// crop="bust" shows head and shoulders (for the banner's face card).
function PixelAvatar({ tier = 0, level = "beginner", body = "male", skin = "starter", crop = "full", size, className = "", title }) {
  const bust = crop === "bust";
  const view = bust ? [4, 0, 24, 24] : [0, 0, W, H];
  const L = leagueStyle(tier);
  const glow = bust ? undefined : tier >= 7 ? `drop-shadow(0 0 8px ${L.color})` : tier >= 4 ? `drop-shadow(0 0 4px ${L.color}99)` : undefined;
  const label = title || `${level} ${body} avatar in ${L.name} league gear`;
  return (
    <svg
      viewBox={view.join(" ")} width={size ? size * (view[2] / view[3]) : undefined} height={size}
      shapeRendering="crispEdges" role="img" aria-label={label}
      className={className} style={{ filter: glow, display: "block" }}
    >
      {avatarRects({ tier, level, body, skin }).map(([x, y, w, h, c], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} fill={c} />
      ))}
    </svg>
  );
}

export default PixelAvatar;
