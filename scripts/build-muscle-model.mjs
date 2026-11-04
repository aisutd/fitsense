// Sculpts the muscle body (src/muscles/body.js) and writes public/models/muscle-body.bin, which the
// Plan tab loads. Re-run after changing the body:
//
//     npm run build:muscles

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { encodeBody, sculptBody } from "../src/muscles/sculpt.js";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "models", "muscle-body.bin");
const started = Date.now();
const body = sculptBody();
const bytes = encodeBody(body);
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, bytes);
console.log(`${body.positions.length / 3} vertices, ${body.indices.length / 3} triangles, ${(bytes.length / 1024).toFixed(0)} KB in ${Date.now() - started} ms -> ${out}`);
