import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { replay, useBeat } from "../fx/beat";
import { crackMesh } from "../fx/crackMesh";

// The page's heartbeat: on each beat (fx/beat.js: a screen change or something logged), a soft
// blue-and-green ring expands from the logo (the element marked data-heartbeat) and fades, lighting
// up a mesh of hairline cracks as its edge passes them. It's kept to the top of the page, ending just
// above the page's title (the first h1, e.g. "HealthScore"), behind the header. Off with reduced
// motion (index.css).

const TITLE_GAP = 12;   // px left clear above the title
// the ring fades out over the last 48px instead of stopping at a hard line
const FADE = "linear-gradient(to bottom, #000 calc(100% - 48px), transparent)";
const FADE_OUT = { maskImage: FADE, WebkitMaskImage: FADE };
const CRACKS = crackMesh();
const same = (a, b) => a && b && Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1 && Math.abs(a.h - b.h) < 1;

function HeartbeatBackdrop() {
  const layer = useRef(null);
  const [area, setArea] = useState(null);   // { x, y: the logo's centre, h: how far down the ripple shows }
  const ripple = useRef(null);
  const cracks = useRef(null);
  const [beats, setBeats] = useState(0);

  // where the logo and the title are (they move when the screen changes or the window resizes)
  const measure = useCallback(() => {
      const logo = document.querySelector("[data-heartbeat]");
      const box = layer.current?.parentElement?.getBoundingClientRect();
      if (!logo || !box) {
        setArea(null);
        return;
      }
      const r = logo.getBoundingClientRect();
      const title = document.querySelector("main h1");
      const bottom = title ? title.getBoundingClientRect().top - TITLE_GAP : r.bottom + 40;
      const next = { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top, h: Math.max(0, bottom - box.top) };
      setArea((current) => (same(current, next) ? current : next));
  }, []);

  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  // a beat: find the logo on the (possibly new) screen, then replay the ring from there
  useBeat(useCallback(() => {
    measure();
    setBeats((n) => n + 1);
  }, [measure]));
  useLayoutEffect(() => {
    if (!beats) return;
    replay(ripple.current);
    replay(cracks.current);
  }, [beats]);

  return (
    <div ref={layer} aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 overflow-hidden"
         style={{ height: area?.h ?? 0, ...FADE_OUT }}>
      {area && <span className="fs-ripple" ref={ripple} style={{ left: area.x, top: area.y }} />}
      {/* the cracks: the whole mesh, shown only in a band that follows the ring's edge (index.css) */}
      {area && (
        <span className="fs-cracks" ref={cracks}
              style={{ "--fs-x": `${area.x}px`, "--fs-y": `${area.y}px`, backgroundImage: CRACKS.image,
                       backgroundSize: `${CRACKS.size}px ${CRACKS.size}px` }} />
      )}
    </div>
  );
}

export default HeartbeatBackdrop;
