import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { GROUPS } from "../muscles/body";
import { MUSCLE_LABELS } from "../muscles/labels";
import { decodeBody } from "../muscles/sculpt";
import { createMuscleScene } from "../muscles/scene";

// Which muscles today's plan day works, on the 3D muscle body (front and back). Primary muscles are
// bright, secondary ones dim; tap a muscle (or its chip) to see which of today's exercises work it.
// Loaded lazily with three.js, so the rest of the app doesn't pay for it.

const MUSCLE = "#ff5d6c";
const DIM = "#9c3a4f";
const LABELS = MUSCLE_LABELS;
const DRAG = 4; // px before a press counts as turning the body instead of a tap

let bodyFile = null;
const loadBody = () =>
  (bodyFile ??= fetch(`${import.meta.env.BASE_URL}models/muscle-body.bin`)
    .then((r) => {
      if (!r.ok) throw new Error(`muscle body: ${r.status}`);
      return r.arrayBuffer();
    })
    .then(decodeBody)
    .catch((err) => {
      bodyFile = null;
      throw err;
    }));

/** {primary, secondary, byMuscle: {muscle: [{name, role}]}} for the day's exercises (stretches left out). */
function musclesOf(exercises) {
  const primary = new Set(), secondary = new Set(), byMuscle = {};
  for (const ex of exercises) {
    if (ex.category === "stretching") continue;
    for (const m of ex.primary_muscles ?? []) {
      primary.add(m);
      (byMuscle[m] ??= []).push({ name: ex.name, role: "primary" });
    }
    for (const m of ex.secondary_muscles ?? []) {
      (byMuscle[m] ??= []).push({ name: ex.name, role: "secondary" });
      if (!primary.has(m)) secondary.add(m);
    }
  }
  for (const m of primary) secondary.delete(m);
  const order = (set) => GROUPS.filter((g) => set.has(g));
  return { primary: order(primary), secondary: order(secondary), byMuscle };
}

function Chip({ muscle, role, active, onHover, onSelect }) {
  const color = role === "primary" ? MUSCLE : DIM;
  return (
    <button
      type="button"
      onPointerEnter={() => onHover(muscle)}
      onPointerLeave={() => onHover(null)}
      onFocus={() => onHover(muscle)}
      onBlur={() => onHover(null)}
      onClick={() => onSelect(muscle)}
      aria-pressed={active}
      className="px-frame px-focus px-2.5 py-1 text-lg transition-colors"
      style={{ "--frame": color, color: active ? "var(--color-night-950)" : role === "primary" ? MUSCLE : "#d98a99", background: active ? color : undefined }}
    >
      {LABELS[muscle] ?? muscle}
    </button>
  );
}

function MuscleMap({ exercises }) {
  const { primary, secondary, byMuscle } = useMemo(() => musclesOf(exercises), [exercises]);
  const canvasRef = useRef(null);
  const sceneRef = useRef(null);
  const press = useRef(null);
  const still = useReducedMotion();
  const [status, setStatus] = useState("loading");
  const [hovered, setHovered] = useState(null);
  const [selected, setSelected] = useState(null);
  const focus = hovered ?? selected;

  useEffect(() => {
    let cancelled = false, scene = null, resizeObs, visibleObs;
    loadBody()
      .then((data) => {
        if (cancelled || !canvasRef.current) return;
        scene = createMuscleScene(canvasRef.current, data, { pixel: 2, still });
        sceneRef.current = scene;
        resizeObs = new ResizeObserver(() => scene.resize());
        resizeObs.observe(canvasRef.current);
        visibleObs = new IntersectionObserver(([entry]) => scene.setRunning(entry.isIntersecting));
        visibleObs.observe(canvasRef.current);
        setStatus("ready");
      })
      .catch(() => !cancelled && setStatus("error"));
    return () => {
      cancelled = true;
      resizeObs?.disconnect();
      visibleObs?.disconnect();
      scene?.dispose();
      sceneRef.current = null;
    };
  }, [still]);

  useEffect(() => {
    sceneRef.current?.setHighlight(primary, secondary);
  }, [primary, secondary, status]);
  useEffect(() => {
    sceneRef.current?.setHover(focus);
  }, [focus, status]);

  const select = (muscle) => setSelected((current) => (current === muscle ? null : muscle));

  function onPointerDown(e) {
    press.current = { x: e.clientX, dragging: false };
  }
  function onPointerMove(e) {
    const scene = sceneRef.current;
    if (!scene) return;
    const p = press.current;
    if (p && (p.dragging || Math.abs(e.clientX - p.x) > DRAG)) {
      if (!p.dragging) e.currentTarget.setPointerCapture(e.pointerId);
      scene.turnBy((e.clientX - p.x) * 0.01);
      press.current = { x: e.clientX, dragging: true };
      return;
    }
    if (e.pointerType === "mouse") setHovered(scene.pick(e.clientX, e.clientY));
  }
  function onPointerUp(e) {
    const p = press.current;
    press.current = null;
    if (p?.dragging || !sceneRef.current) return;
    const muscle = sceneRef.current.pick(e.clientX, e.clientY);
    setSelected(muscle && muscle !== selected ? muscle : null);
  }

  const role = (m) => (primary.includes(m) ? "primary" : secondary.includes(m) ? "secondary" : null);
  const focusWork = focus ? byMuscle[focus] ?? [] : [];
  const summary = [
    primary.length && `primary: ${primary.map((m) => LABELS[m]).join(", ")}`,
    secondary.length && `secondary: ${secondary.map((m) => LABELS[m]).join(", ")}`,
  ].filter(Boolean).join("; ");

  return (
    <section className="px-frame mt-8 bg-night-800/90 p-5 sm:p-6" style={{ "--frame": "var(--color-night-600)" }} aria-labelledby="muscles-today">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="muscles-today" className="text-3xl" style={{ color: MUSCLE }}>Muscles worked today</h2>
        <p className="text-muted">Tap a muscle to see what works it</p>
      </div>

      <div className="mt-4 grid gap-6 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] md:items-center">
        <div className="px-frame relative bg-night-900/70" style={{ "--frame": "var(--color-night-700)" }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Body map of today's workout, ${summary || "no muscles listed"}`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={() => setHovered(null)}
            className="block h-[300px] w-full cursor-grab touch-pan-y sm:h-[380px]"
            style={{ imageRendering: "pixelated" }}
          />
          {status !== "ready" && (
            <p role="status" className="absolute inset-x-0 top-0 flex h-[300px] items-center justify-center text-lg text-muted sm:h-[380px]">
              {status === "loading" ? "Loading the muscle map…" : "Couldn't load the muscle map."}
            </p>
          )}
          <div aria-hidden="true" className="flex justify-around border-t-[3px] border-night-700 py-1.5 text-sm tracking-[0.2em] text-muted">
            <span>FRONT</span>
            <span>BACK</span>
          </div>
        </div>

        <div>
          {primary.length > 0 && (
            <>
              <p className="text-sm uppercase tracking-wider text-muted">Primary</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {primary.map((m) => <Chip key={m} muscle={m} role="primary" active={focus === m} onHover={setHovered} onSelect={select} />)}
              </div>
            </>
          )}
          {secondary.length > 0 && (
            <>
              <p className="mt-4 text-sm uppercase tracking-wider text-muted">Secondary</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {secondary.map((m) => <Chip key={m} muscle={m} role="secondary" active={focus === m} onHover={setHovered} onSelect={select} />)}
              </div>
            </>
          )}
          {!primary.length && !secondary.length && <p className="text-lg text-muted">Today's exercises don't list their muscles.</p>}

          <div className="mt-5 min-h-[5.5rem] border-t-[3px] border-night-700 pt-4" aria-live="polite">
            {focus ? (
              <>
                <p className="text-xl" style={{ color: role(focus) === "secondary" ? "#d98a99" : role(focus) ? MUSCLE : undefined }}>
                  {LABELS[focus] ?? focus}
                  <span className="text-base text-muted"> · {role(focus) ?? "resting today"}</span>
                </p>
                {focusWork.length > 0 ? (
                  <ul className="mt-1 text-muted">
                    {focusWork.map((w) => (
                      <li key={`${w.name}-${w.role}`}>
                        {w.name} <span className="text-sm">({w.role})</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-muted">None of today's exercises work it.</p>
                )}
              </>
            ) : (
              <p className="text-muted">Bright muscles do most of the work today, dim ones help. Drag the body to turn it.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default MuscleMap;
