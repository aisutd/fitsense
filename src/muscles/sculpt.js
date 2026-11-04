// Sculpts the body from src/muscles/body.js into a triangle mesh (surface nets over a signed distance
// field) and labels every vertex with its muscle. Runs at build time (scripts/build-muscle-model.mjs);
// the app only loads the result.
//
// Region codes per vertex: 0..16 a muscle group (GROUPS), DECOR codes for painted details, SKIN for bare
// skin, SEAM for the line between two groups (or a muscle's edge), FINE for the line between two parts of
// one group (the ab grid, deltoid heads) or a muscle's edge. groupOf keeps the group under a line, for coloring.

import { Euler, Matrix4 } from "three";
import { DECOR, GROUPS, defineBody } from "./body.js";

export const SKIN = -1;
export const SEAM = -2;
export const FINE = -3;

const RHO = 0.022; // how far inside a footprint a muscle reaches full height
const GROOVE_WIDTH = 0.016;
const GROOVE_DEPTH = 0.005;
const FOOTPRINT = 1.3; // footprints are drawn a bit larger than their numbers so muscles tile

function rotInverse(rot) {
  return new Matrix4().makeRotationFromEuler(new Euler(...(rot || [0, 0, 0]))).invert().elements;
}

function sdf(p, x, y, z) {
  if (p.t === 0) {
    const px = x - p.c[0], py = y - p.c[1], pz = z - p.c[2], e = p.m;
    const lx = (e[0] * px + e[4] * py + e[8] * pz) / p.r[0];
    const ly = (e[1] * px + e[5] * py + e[9] * pz) / p.r[1];
    const lz = (e[2] * px + e[6] * py + e[10] * pz) / p.r[2];
    const k0 = Math.hypot(lx, ly, lz), k1 = Math.hypot(lx / p.r[0], ly / p.r[1], lz / p.r[2]);
    return k1 > 1e-9 ? (k0 * (k0 - 1)) / k1 : -Math.min(...p.r);
  }
  const a = p.a, b = p.b, pax = x - a[0], pay = y - a[1], paz = z - a[2];
  const bax = b[0] - a[0], bay = b[1] - a[1], baz = b[2] - a[2];
  const h = Math.min(1, Math.max(0, (pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz)));
  return Math.hypot(pax - bax * h, pay - bay * h, paz - baz * h) - (p.r1 + (p.r2 - p.r1) * h);
}

const smin = (a, b, k) => {
  const h = Math.max(k - Math.abs(a - b), 0) / k;
  return Math.min(a, b) - h * h * k * 0.25;
};
const dome = (d) => {
  const t = Math.min(1, Math.max(0, -d / RHO));
  return t * t * (3 - 2 * t);
};

function collect() {
  const base = [], parts = [];
  defineBody({
    bell(c, r, k = 0.06, rot) {
      base.push({ t: 0, c, r, m: rotInverse(rot), k, R: Math.max(...r) });
    },
    bcap(a, b, r1, r2, k = 0.05) {
      const c = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
      base.push({ t: 1, a, b, r1, r2, k, c, R: Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) / 2 + Math.max(r1, r2) });
    },
    m(name, c, r, rot, lift = 0.016) {
      const g = name in DECOR ? DECOR[name] : GROUPS.indexOf(name);
      if (g < 0) throw new Error(`unknown muscle ${name}`);
      const rr = [r[0] * FOOTPRINT, r[1] * FOOTPRINT, r[2]];
      parts.push({ t: 0, c, r: rr, m: rotInverse(rot), g, lift, R: Math.max(...rr) });
    },
  });
  return { base, parts };
}

export function sculptBody({ cell = 0.011 } = {}) {
  const { base, parts } = collect();
  const scores = new Float32Array(256), owners = new Int16Array(256);

  function baseField(x, y, z) {
    let d = 1e9;
    for (const p of base) {
      const far = Math.hypot(x - p.c[0], y - p.c[1], z - p.c[2]) - p.R;
      d = smin(d, far > 0.12 ? far : sdf(p, x, y, z), p.k);
    }
    return d;
  }

  // Each footprint scores how deep a point sits inside it. The owner is the top score; a line runs where
  // the top score ties with another group's (strong) or with another part of the same group (fine).
  function relief(x, y, z) {
    let lift = 0, n = 0, best = -1e9, owner = -1;
    for (let i = 0; i < parts.length; i++) {
      const p = parts[i];
      if (Math.hypot(x - p.c[0], y - p.c[1], z - p.c[2]) > p.R + 0.03) continue;
      const score = -sdf(p, x, y, z);
      const raise = p.lift * dome(-score);
      if (Math.abs(raise) > Math.abs(lift)) lift = raise;
      scores[n] = score;
      owners[n] = i;
      n++;
      if (score > best) {
        best = score;
        owner = i;
      }
    }
    let otherGroup = -1e9, sameGroup = -1e9;
    const g = owner >= 0 ? parts[owner].g : -1;
    for (let j = 0; j < n; j++) {
      if (owners[j] === owner) continue;
      if (parts[owners[j]].g === g) sameGroup = Math.max(sameGroup, scores[j]);
      else otherGroup = Math.max(otherGroup, scores[j]);
    }
    let groove = 0;
    if (best > -0.004) {
      groove = Math.max(
        GROOVE_DEPTH * Math.max(0, 1 - (best - otherGroup) / GROOVE_WIDTH),
        GROOVE_DEPTH * 0.45 * Math.max(0, 1 - (best - sameGroup) / GROOVE_WIDTH),
        GROOVE_DEPTH * 0.6 * Math.max(0, 1 - Math.abs(best) / 0.006),
      );
    }
    return { height: lift - groove, owner, best, otherGroup, sameGroup };
  }

  const field = (x, y, z) => {
    const d = baseField(x, y, z);
    return d > 0.06 ? d : d - relief(x, y, z).height;
  };

  // surface nets: one vertex per cell the surface crosses, one quad per crossed grid edge
  const X0 = -0.5, Y0 = -0.4, Z0 = -0.22;
  const NX = Math.ceil(1.0 / cell), NY = Math.ceil(2.14 / cell), NZ = Math.ceil(0.44 / cell);
  const PX = NX + 1, PY = NY + 1, PZ = NZ + 1;
  const F = new Float32Array(PX * PY * PZ);
  for (let k = 0; k < PZ; k++)
    for (let j = 0; j < PY; j++)
      for (let i = 0; i < PX; i++) F[i + PX * (j + PY * k)] = field(X0 + i * cell, Y0 + j * cell, Z0 + k * cell);

  const corners = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0], [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]];
  const edges = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
  const cellVertex = new Int32Array(NX * NY * NZ).fill(-1);
  const pos = [], v = new Float32Array(8);
  for (let k = 0; k < NZ; k++)
    for (let j = 0; j < NY; j++)
      for (let i = 0; i < NX; i++) {
        let inside = 0;
        for (let c = 0; c < 8; c++) {
          const q = corners[c];
          v[c] = F[i + q[0] + PX * (j + q[1] + PY * (k + q[2]))];
          if (v[c] < 0) inside++;
        }
        if (inside === 0 || inside === 8) continue;
        let sx = 0, sy = 0, sz = 0, n = 0;
        for (const [a, b] of edges) {
          if (v[a] < 0 === v[b] < 0) continue;
          const t = v[a] / (v[a] - v[b]), qa = corners[a], qb = corners[b];
          sx += qa[0] + (qb[0] - qa[0]) * t;
          sy += qa[1] + (qb[1] - qa[1]) * t;
          sz += qa[2] + (qb[2] - qa[2]) * t;
          n++;
        }
        cellVertex[i + NX * (j + NY * k)] = pos.length / 3;
        pos.push(X0 + (i + sx / n) * cell, Y0 + (j + sy / n) * cell, Z0 + (k + sz / n) * cell);
      }
  const C = (i, j, k) => cellVertex[i + NX * (j + NY * k)];
  const idx = [];
  for (let k = 1; k < NZ; k++)
    for (let j = 1; j < NY; j++)
      for (let i = 1; i < NX; i++) {
        const inside = F[i + PX * (j + PY * k)] < 0;
        if (F[i + 1 + PX * (j + PY * k)] < 0 !== inside) {
          const a = C(i, j - 1, k - 1), b = C(i, j, k - 1), c = C(i, j, k), d = C(i, j - 1, k);
          if (inside) idx.push(a, b, c, a, c, d);
          else idx.push(a, c, b, a, d, c);
        }
        if (F[i + PX * (j + 1 + PY * k)] < 0 !== inside) {
          const a = C(i - 1, j, k - 1), b = C(i, j, k - 1), c = C(i, j, k), d = C(i - 1, j, k);
          if (inside) idx.push(a, c, b, a, d, c);
          else idx.push(a, b, c, a, c, d);
        }
        if (F[i + PX * (j + PY * (k + 1))] < 0 !== inside) {
          const a = C(i - 1, j - 1, k), b = C(i, j - 1, k), c = C(i, j, k), d = C(i - 1, j, k);
          if (inside) idx.push(a, b, c, a, c, d);
          else idx.push(a, c, b, a, d, c);
        }
      }

  // Each vertex belongs to the footprint it sits deepest in. Lines run along mesh edges whose ends
  // belong to different footprints: heavy (both sides of the edge) between
  // muscle groups, fine (one side) between parts of one group and along a muscle's edge with bare skin. Painted
  // details (eyes) get no outline.
  const nv = pos.length / 3;
  const owner = new Int16Array(nv), region = new Int8Array(nv), groupOf = new Int8Array(nv);
  for (let q = 0; q < nv; q++) {
    const r = relief(pos[q * 3], pos[q * 3 + 1], pos[q * 3 + 2]);
    owner[q] = r.best > 0 ? r.owner : -1;
    groupOf[q] = region[q] = owner[q] < 0 ? SKIN : parts[owner[q]].g;
  }
  const isMuscle = (g) => g >= 0 && g < GROUPS.length;
  for (let f = 0; f < idx.length; f += 3)
    for (let e = 0; e < 3; e++) {
      const a = idx[f + e], b = idx[f + ((e + 1) % 3)];
      if (owner[a] === owner[b]) continue;
      const ga = groupOf[a], gb = groupOf[b], side = owner[a] > owner[b] ? a : b;
      if (isMuscle(ga) && isMuscle(gb) && ga !== gb) region[a] = region[b] = SEAM; // group lines: both sides
      else if (ga === gb ? ga !== DECOR.eyes : isMuscle(ga) || isMuscle(gb)) {
        if (region[side] !== SEAM) region[side] = FINE;
      }
    }
  return { positions: new Float32Array(pos), indices: new Uint32Array(idx), region, groupOf };
}

// Compact binary: "FSMB", version, counts, bounds, then positions as uint16 within the bounds,
// indices (uint16 when they fit), region and groupOf as int8.
export function encodeBody({ positions, indices, region, groupOf }) {
  const nv = positions.length / 3, ni = indices.length, wide = nv > 65535;
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i++) {
    min[i % 3] = Math.min(min[i % 3], positions[i]);
    max[i % 3] = Math.max(max[i % 3], positions[i]);
  }
  const header = 4 + 4 + 4 + 4 + 24;
  const size = header + nv * 6 + ni * (wide ? 4 : 2) + nv * 2;
  const buf = new ArrayBuffer(size + (4 - (size % 4)) % 4);
  const dv = new DataView(buf);
  [70, 83, 77, 66].forEach((ch, i) => dv.setUint8(i, ch));
  dv.setUint32(4, wide ? 2 : 1, true);
  dv.setUint32(8, nv, true);
  dv.setUint32(12, ni, true);
  for (let a = 0; a < 3; a++) {
    dv.setFloat32(16 + a * 4, min[a], true);
    dv.setFloat32(28 + a * 4, max[a], true);
  }
  let o = header;
  for (let i = 0; i < positions.length; i++, o += 2) {
    const a = i % 3;
    dv.setUint16(o, Math.round(((positions[i] - min[a]) / (max[a] - min[a])) * 65535), true);
  }
  for (let i = 0; i < ni; i++, o += wide ? 4 : 2) wide ? dv.setUint32(o, indices[i], true) : dv.setUint16(o, indices[i], true);
  for (let i = 0; i < nv; i++, o++) dv.setInt8(o, region[i]);
  for (let i = 0; i < nv; i++, o++) dv.setInt8(o, groupOf[i]);
  return new Uint8Array(buf);
}

export function decodeBody(buffer) {
  const dv = new DataView(buffer);
  if (String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3)) !== "FSMB") throw new Error("not a muscle body file");
  const wide = dv.getUint32(4, true) === 2, nv = dv.getUint32(8, true), ni = dv.getUint32(12, true);
  const min = [0, 1, 2].map((a) => dv.getFloat32(16 + a * 4, true)), max = [0, 1, 2].map((a) => dv.getFloat32(28 + a * 4, true));
  let o = 40;
  const positions = new Float32Array(nv * 3);
  for (let i = 0; i < nv * 3; i++, o += 2) {
    const a = i % 3;
    positions[i] = min[a] + (dv.getUint16(o, true) / 65535) * (max[a] - min[a]);
  }
  const indices = wide ? new Uint32Array(ni) : new Uint16Array(ni);
  for (let i = 0; i < ni; i++, o += wide ? 4 : 2) indices[i] = wide ? dv.getUint32(o, true) : dv.getUint16(o, true);
  const region = new Int8Array(buffer.slice(o, o + nv));
  const groupOf = new Int8Array(buffer.slice(o + nv, o + 2 * nv));
  return { positions, indices, region, groupOf };
}
