import { useEffect, useRef } from "react";
import { clearFrame, composite, createFrame, createFx } from "../fx/pixelfx/core/index.js";

// Plays one pixelfx effect on a small canvas scaled up with crisp pixels. (x, y) is where the effect's
// origin lands, in the parent's coordinates. Transparent background: glow reads as light over the dark UI.

const MAX_STEP = 0.05;

function PixelFx({ effect, options, x, y, scale = 2, delay = 0, onDone }) {
  const canvasRef = useRef(null);
  const [w, h] = effect.meta.size;
  const [ox, oy] = effect.meta.origin;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const frame = createFrame(w, h, -ox, -oy);
    const image = ctx.createImageData(w, h);
    const fx = createFx(effect, options);
    let raf = 0, last = null, waited = 0;

    const tick = (now) => {
      const dt = last === null ? 0 : Math.min(MAX_STEP, (now - last) / 1000);
      last = now;
      if (waited < delay) {
        waited += dt;
      } else {
        fx.update(dt);
        clearFrame(frame);
        fx.draw(frame);
        composite(frame, image.data, null);
        ctx.putImageData(image, 0, 0);
        if (fx.done()) {
          ctx.clearRect(0, 0, w, h);
          onDone?.();
          return;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // one run per mount: the parent remounts it (with a new key) to play it again
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <canvas
      ref={canvasRef}
      width={w}
      height={h}
      aria-hidden="true"
      className="pointer-events-none absolute"
      style={{ left: x - ox * scale, top: y - oy * scale, width: w * scale, height: h * scale, imageRendering: "pixelated" }}
    />
  );
}

export default PixelFx;
