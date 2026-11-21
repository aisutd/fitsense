import { useEffect, useRef, useState } from "react";
import { BEAT_MS, syncToBeat } from "./BrandMark";

// The page's heartbeat: each beat, a soft blue-and-green ring expands from the logo (the element
// marked data-heartbeat) and fades. It's kept to the top of the page, ending just above the page's
// title (the first h1, e.g. "HealthScore"), behind the header. Same clock as the logo (syncToBeat), so
// they always beat together. Off with reduced motion (index.css).

const TITLE_GAP = 12;   // px left clear above the title
// the ring fades out over the last 48px instead of stopping at a hard line
const FADE = "linear-gradient(to bottom, #000 calc(100% - 48px), transparent)";
const FADE_OUT = { maskImage: FADE, WebkitMaskImage: FADE };
const same = (a, b) => a && b && Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1 && Math.abs(a.h - b.h) < 1;

function HeartbeatBackdrop() {
  const layer = useRef(null);
  const [area, setArea] = useState(null);   // { x, y: the logo's centre, h: how far down the ripple shows }

  useEffect(() => {
    // where the logo and the title are (they move when the screen changes or the window resizes)
    const measure = () => {
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
    };
    measure();
    const soon = window.setTimeout(measure, 300);   // once the screen has laid out
    const timer = window.setInterval(measure, BEAT_MS / 2);
    window.addEventListener("resize", measure);
    return () => {
      window.clearTimeout(soon);
      window.clearInterval(timer);
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <div ref={layer} aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 overflow-hidden"
         style={{ height: area?.h ?? 0, ...FADE_OUT }}>
      {area && <span className="fs-ripple" ref={syncToBeat} style={{ left: area.x, top: area.y }} />}
    </div>
  );
}

export default HeartbeatBackdrop;
