// Renders the muscle body (front and back side by side) in the app's pixel style: toon shading lit from
// the top left like the pixel icons, a dark outline, and a low-resolution render scaled up with crisp
// pixels. Muscles are colored per vertex, so changing the highlight is just a color update.

import {
  AmbientLight, BackSide, BufferAttribute, BufferGeometry, Color, DataTexture, DirectionalLight, Group, Mesh,
  MeshBasicMaterial, MeshToonMaterial, NearestFilter, PerspectiveCamera, Raycaster, Scene, Vector2, WebGLRenderer,
} from "three";
import { DECOR, GROUPS } from "./body.js";
import { FINE, SEAM, SKIN } from "./sculpt.js";

const COLORS = {
  primary: new Color("#ff5d6c"),
  secondary: new Color("#9c3a4f"),
  resting: new Color("#3a4f8a"),
  skin: new Color("#2b3b72"),
  seam: new Color("#0a1022"),
  hover: new Color("#ffd1d6"),
  [DECOR.eyes]: new Color("#0a1022"),
  [DECOR.hand]: new Color("#2b3b72"),
};
const FINE_SHADE = 0.62;
const SWAY = 0.35;

export function createMuscleScene(canvas, data, { pixel = 2, still = false } = {}) {
  const { positions, indices, region, groupOf } = data;
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(positions, 3));
  geometry.setIndex(new BufferAttribute(indices, 1));
  geometry.computeVertexNormals();
  const colors = new Float32Array(positions.length);
  geometry.setAttribute("color", new BufferAttribute(colors, 3));

  const renderer = new WebGLRenderer({ canvas, antialias: false, alpha: true });
  renderer.setClearColor(0x000000, 0);
  const scene = new Scene();
  scene.add(new AmbientLight(0xffffff, 0.6));
  const sun = new DirectionalLight(0xffffff, 2.3);
  sun.position.set(-2.2, 3, 3.2);
  scene.add(sun);
  const camera = new PerspectiveCamera(30, 1, 0.1, 50);
  // far enough back to fit both figures in the canvas's width as well as its height
  const SPAN = 2.25, HEIGHT_DISTANCE = 4.05;
  let framing = null;
  function aim(x = 0, y = 0.665, distance) {
    framing = distance === undefined ? null : [x, y, distance];
    const fit = Math.max(HEIGHT_DISTANCE, SPAN / (2 * Math.tan((camera.fov * Math.PI) / 360) * camera.aspect));
    camera.position.set(x, y, distance ?? fit);
    camera.lookAt(x, y, 0);
  }
  aim();

  const ramp = new DataTexture(new Uint8Array([80, 80, 80, 255, 165, 165, 165, 255, 255, 255, 255, 255]), 3, 1);
  ramp.minFilter = ramp.magFilter = NearestFilter;
  ramp.needsUpdate = true;
  const material = new MeshToonMaterial({ vertexColors: true, gradientMap: ramp });
  const outline = new MeshBasicMaterial({ color: 0x04070e, side: BackSide });
  outline.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>", "vec3 transformed = position + normal * 0.009;");
  };

  const bodies = [];
  function figure(x) {
    const g = new Group();
    const mesh = new Mesh(geometry, material);
    g.add(mesh, new Mesh(geometry, outline));
    g.position.x = x;
    scene.add(g);
    bodies.push(mesh);
    return g;
  }
  const front = figure(-0.53), back = figure(0.53);

  let primary = new Set(), secondary = new Set(), hovered = null;
  function paint() {
    for (let v = 0; v < region.length; v++) {
      const r = region[v], g = groupOf[v];
      const name = g >= 0 && g < GROUPS.length ? GROUPS[g] : null;
      let c;
      if (r === SEAM || (r === FINE && !name && g !== SKIN)) c = COLORS.seam; // finger lines are drawn dark too
      else if (r === SKIN || g === SKIN) c = COLORS.skin;
      else if (!name) c = COLORS[g];
      else if (name === hovered) c = COLORS.hover;
      else if (primary.has(name)) c = COLORS.primary;
      else if (secondary.has(name)) c = COLORS.secondary;
      else c = COLORS.resting;
      const k = r === FINE ? FINE_SHADE : 1;
      colors[v * 3] = c.r * k;
      colors[v * 3 + 1] = c.g * k;
      colors[v * 3 + 2] = c.b * k;
    }
    geometry.attributes.color.needsUpdate = true;
  }

  let px = pixel;
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setPixelRatio(1);
    renderer.setSize(Math.max(1, Math.round(w / px)), Math.max(1, Math.round(h / px)), false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    framing ? aim(...framing) : aim();
  }

  let turn = 0, t = 0, auto = !still, running = false, frame = 0;
  function draw() {
    const sway = auto ? Math.sin(t * 0.8) * SWAY : 0;
    front.rotation.y = turn + sway;
    back.rotation.y = Math.PI + turn + sway;
    renderer.render(scene, camera);
  }
  function loop() {
    t += 0.016;
    draw();
    frame = requestAnimationFrame(loop);
  }

  const ray = new Raycaster(), pointer = new Vector2();
  paint();
  resize();
  draw();

  return {
    setHighlight(p, s) {
      primary = new Set(p);
      secondary = new Set(s);
      paint();
      draw();
    },
    setHover(name) {
      if (name === hovered) return;
      hovered = name;
      paint();
      draw();
    },
    /** The muscle group under a point on the canvas, or null. */
    pick(clientX, clientY) {
      const r = canvas.getBoundingClientRect();
      pointer.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(bodies, false)[0];
      const g = hit ? groupOf[hit.face.a] : -1;
      return g >= 0 && g < GROUPS.length ? GROUPS[g] : null;
    },
    /** Point the camera somewhere else (defaults frame both figures). */
    lookAt(x, y, distance) {
      aim(x, y, distance);
      draw();
    },
    turnBy(dx) {
      auto = false;
      turn += dx;
      draw();
    },
    setPixel(value) {
      px = value;
      resize();
      draw();
    },
    /** Animate (the gentle sway) only while the canvas is on screen. */
    setRunning(on) {
      if (on === running) return;
      running = on;
      if (on && !still) frame = requestAnimationFrame(loop);
      else cancelAnimationFrame(frame);
    },
    resize() {
      resize();
      draw();
    },
    dispose() {
      cancelAnimationFrame(frame);
      geometry.dispose();
      material.dispose();
      outline.dispose();
      ramp.dispose();
      renderer.dispose();
    },
  };
}
