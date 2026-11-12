import { leagueStyle } from "../game/leagues";

// Pixel-art player: the fitness level sets the build, the league colours the clothes and
// unlocks accessories (they stack), the body is the player's pick (male / female).
// Drawn on a 32 x 44 grid as SVG rects so it stays crisp at any size.
const W = 32;
const H = 44;
const OY = 3; // room above the head for the crown

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

export function avatarRects({ tier = 0, level = "beginner", body = "male" }) {
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
function PixelAvatar({ tier = 0, level = "beginner", body = "male", crop = "full", size, className = "", title }) {
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
      {avatarRects({ tier, level, body }).map(([x, y, w, h, c], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} fill={c} />
      ))}
    </svg>
  );
}

export default PixelAvatar;
