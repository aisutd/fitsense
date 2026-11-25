import { useEffect } from "react";

// The page's heartbeat: one beat on demand, when a screen appears (its logo mounts: ScreenLayout.jsx)
// or something is logged (api.js), instead of on a timer. beat() tells every heartbeat element (the logo's line and glow,
// the backdrop's ripple and cracks) to replay its one-shot CSS animation (index.css) together.

const EVENT = "fitsense:beat";
// The animations open with the line travelling toward the logo; start a little way in, so the beat
// lands about half a second after whatever triggered it.
const LEAD_MS = 400;

export function beat() {
  window.dispatchEvent(new Event(EVENT));
}

// Replay an element's heartbeat animation from the top (just past the lead-in).
export function replay(element) {
  if (!element?.getAnimations) return;
  for (const animation of element.getAnimations()) {
    animation.cancel();
    animation.currentTime = LEAD_MS;
    animation.play();
  }
}

// Call fn on every beat (fn finds its elements when the beat comes).
export function useBeat(fn) {
  useEffect(() => {
    window.addEventListener(EVENT, fn);
    return () => window.removeEventListener(EVENT, fn);
  }, [fn]);
}
