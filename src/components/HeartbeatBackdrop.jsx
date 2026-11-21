import { useEffect, useRef, useState } from "react";
import { BEAT_MS, beatDelay } from "./BrandMark";

// The page's heartbeat: each beat, a soft blue-and-green ring expands from the logo (the element
// marked data-heartbeat) out across the background and fades, as the logo glows. It sits between the
// pixel background and the page, so cards and panels show it faintly through. Same clock as the logo
// (beatDelay), so they always beat together. Off with reduced motion (index.css).

const same = (a, b) => a && b && Math.abs(a.x - b.x) < 1 && Math.abs(a.y - b.y) < 1;

function HeartbeatBackdrop() {
  const layer = useRef(null);
  const [origin, setOrigin] = useState(null);
  const [delay] = useState(beatDelay);

  useEffect(() => {
    // where the logo is, in this layer's coordinates (it moves when the screen changes or the window resizes)
    const measure = () => {
      const logo = document.querySelector("[data-heartbeat]");
      const box = layer.current?.getBoundingClientRect();
      if (!logo || !box) {
        setOrigin(null);
        return;
      }
      const r = logo.getBoundingClientRect();
      const next = { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top };
      setOrigin((current) => (same(current, next) ? current : next));
    };
    measure();
    const timer = window.setInterval(measure, BEAT_MS);
    window.addEventListener("resize", measure);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("resize", measure);
    };
  }, []);

  return (
    <div ref={layer} aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {origin && <span className="fs-ripple" style={{ left: origin.x, top: origin.y, animationDelay: delay }} />}
    </div>
  );
}

export default HeartbeatBackdrop;
