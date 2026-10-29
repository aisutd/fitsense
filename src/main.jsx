import React from "react";
import { createRoot } from "react-dom/client";
import { ReactLenis } from "lenis/react";
import { MotionConfig } from "motion/react";
import App from "./App";
import "./index.css";

// MOUNT TO DOM
// ReactLenis gives the whole page smooth scrolling; MotionConfig turns
// animations off for people who prefer reduced motion.

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ReactLenis root options={{ lerp: 0.1, smoothWheel: true }}>
      <MotionConfig reducedMotion="user">
        <App />
      </MotionConfig>
    </ReactLenis>
  </React.StrictMode>
);
