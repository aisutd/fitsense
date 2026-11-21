import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import PixelFx from "./PixelFx";
import DecryptedText from "./reactbits/DecryptedText";
import * as collectBurst from "../fx/pixelfx/fx/pickups/collect-burst.js";
import * as confetti from "../fx/pixelfx/fx/ui/confetti.js";
import { announcerMode, onAnnounce, RARITY, rewardLine } from "../achievements";

// The System announces achievements one at a time in a pixel message box: the title, the dry
// one-liner under it, then its commentary typed out (or, in Plain mode, what it was for). Click,
// Enter or Space finishes the typing, then moves on; Escape closes them all. It waits a moment so
// the log's own reward pop-up plays first.

const TITLE = { fontFamily: '"FitSense Title", "FitSense Pixel", monospace', fontWeight: 400 };
const CHARS_PER_SECOND = 45;
const START_DELAY = 900;   // ms, after the reward pop-up has had its moment

// pixelfx palettes, dark to light
const PALETTES = {
  common: ["#0c1020", "#1b2236", "#2d3650", "#4a5470", "#6f7a96", "#a3adc4", "#d6dcea", "#ffffff"],
  uncommon: ["#04160c", "#0a2e18", "#12502a", "#1b7a3e", "#2aae58", "#42e08b", "#b6f7d2", "#ffffff"],
  rare: ["#04121c", "#08263a", "#0e4566", "#13709e", "#1fa3d6", "#4fd8ff", "#b8f1ff", "#ffffff"],
  epic: ["#14051f", "#2c0a45", "#4b137a", "#6e22b0", "#9a45e0", "#c77dff", "#e8ccff", "#ffffff"],
  legendary: ["#2a1405", "#5c3008", "#9a5a0e", "#d48e18", "#f5b92c", "#ffde5e", "#fff4bc", "#ffffff"],
};

function useTyped(text, enabled) {
  const [shown, setShown] = useState(enabled ? 0 : text.length);
  useEffect(() => {
    if (!enabled) {
      setShown(text.length);
      return undefined;
    }
    setShown(0);
    const timer = window.setInterval(() => {
      setShown((n) => {
        if (n >= text.length) {
          window.clearInterval(timer);
          return n;
        }
        return n + 1;
      });
    }, 1000 / CHARS_PER_SECOND);
    return () => window.clearInterval(timer);
  }, [text, enabled]);
  return [text.slice(0, shown), shown >= text.length, () => setShown(text.length)];
}

function Message({ item, index, count, mode, still, onNext, onClose }) {
  const rarity = RARITY[item.rarity] ?? RARITY.common;
  const body = mode === "plain" ? item.plain : item.commentary;
  const [typed, finished, finish] = useTyped(body, !still && mode !== "plain");
  const boxRef = useRef(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => setWidth(boxRef.current?.offsetWidth ?? 0), []);

  const advance = useCallback(() => (finished ? onNext() : finish()), [finished, finish, onNext]);
  useEffect(() => {
    const onKey = (e) => {
      const typing = e.target.closest?.("input, textarea, select, [contenteditable='true']");
      if (typing) return;   // don't take keys from a form the player is filling in
      if (e.key === "Escape") onClose();
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        advance();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advance, onClose]);

  const big = item.rarity === "epic" || item.rarity === "legendary";
  return (
    <motion.div
      initial={still ? { opacity: 0 } : { opacity: 0, y: -16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={still ? { opacity: 0 } : { opacity: 0, y: -10 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className="pointer-events-auto relative w-full max-w-xl"
    >
      {!still && width > 0 && (
        <div aria-hidden="true" className="pointer-events-none absolute inset-0">
          <PixelFx effect={collectBurst} options={{ palette: PALETTES[item.rarity] ?? PALETTES.common, light: big ? 1.5 : 1, seed: item.id }}
            x={width / 2} y={8} scale={big ? 3 : 2} />
          {big && (
            <>
              <PixelFx effect={confetti} options={{ seed: item.id + 3 }} x={width * 0.2} y={220} scale={2} delay={0.2} />
              <PixelFx effect={confetti} options={{ seed: item.id + 7 }} x={width * 0.8} y={220} scale={2} delay={0.35} />
            </>
          )}
        </div>
      )}
      <section
        ref={boxRef}
        role="status"
        aria-live="polite"
        onClick={advance}
        className="px-frame cursor-pointer bg-night-950/95 p-5 shadow-[0_0_40px_#000a] sm:p-6"
        style={{ "--frame": rarity.color, boxShadow: `0 0 28px ${rarity.color}55` }}
      >
        <div className="flex items-center justify-between gap-3 text-sm tracking-[0.2em]">
          <span className="text-cyan">▣ SYSTEM MESSAGE</span>
          {count > 1 && <span className="text-muted">{index + 1} / {count}</span>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="text-lg tracking-[0.15em]" style={{ ...TITLE, color: rarity.color }}>
            NEW ACHIEVEMENT!
          </p>
          <span className="border-2 px-1.5 text-xs uppercase leading-5 tracking-widest"
            style={{ borderColor: rarity.color, color: rarity.color }}>
            {rarity.label}
          </span>
        </div>
        <h2 className="mt-2 text-3xl leading-tight sm:text-4xl" style={{ ...TITLE, textShadow: `0 0 14px ${rarity.color}88` }}>
          {/* the title decrypts as the message arrives (React Bits DecryptedText) */}
          {still ? item.name : (
            <DecryptedText text={item.name} animateOn="view" sequential revealDirection="start" speed={35}
              characters="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&@$" />
          )}
        </h2>
        {mode !== "plain" && <p className="mt-1 italic text-muted">{item.description}</p>}
        <div className="my-4 h-[3px] w-full" style={{ background: `linear-gradient(90deg, ${rarity.color}, transparent)` }} aria-hidden="true" />
        <p className="min-h-[3.5rem] text-lg leading-snug">
          {/* typed out on screen; screen readers get the whole line once */}
          <span aria-hidden="true">{typed}</span>
          {!finished && <span aria-hidden="true" className="animate-pulse text-cyan">▌</span>}
          <span className="sr-only">{body}</span>
        </p>
        <p className="mt-4 text-gold">{rewardLine(item)}</p>
        <div className="mt-5 flex items-center justify-between gap-3">
          {count - index > 1 ? (
            <button type="button" onClick={(e) => { e.stopPropagation(); onClose(); }}
              className="px-focus text-sm text-muted hover:text-cyan">
              Skip all
            </button>
          ) : <span />}
          <button type="button" onClick={(e) => { e.stopPropagation(); advance(); }}
            className="px-focus border-2 px-3 py-1 text-lg leading-tight"
            style={{ borderColor: rarity.color, color: rarity.color }}>
            {!finished ? "▸▸ Skip" : index + 1 < count ? "Next ▸" : "Got it"}
          </button>
        </div>
      </section>
    </motion.div>
  );
}

function Announcer() {
  const [queue, setQueue] = useState([]);
  const [index, setIndex] = useState(0);
  const [ready, setReady] = useState(false);
  const [mode, setMode] = useState(announcerMode);
  const still = useReducedMotion();

  useEffect(() => onAnnounce((items) => {
    setQueue((q) => [...q, ...items]);
    window.setTimeout(() => setReady(true), START_DELAY);
  }), []);
  useEffect(() => {
    const onMode = (e) => setMode(e.detail);
    window.addEventListener("fitsense:announcer-mode", onMode);
    return () => window.removeEventListener("fitsense:announcer-mode", onMode);
  }, []);

  const close = useCallback(() => {
    setQueue([]);
    setIndex(0);
    setReady(false);
  }, []);
  const next = useCallback(() => {
    if (index + 1 < queue.length) setIndex(index + 1);
    else close();
  }, [index, queue.length, close]);

  const item = ready ? queue[index] : null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-[12vh] z-[60] flex justify-center px-4">
      <AnimatePresence mode="wait">
        {item && (
          <Message key={item.id} item={item} index={index} count={queue.length} mode={mode} still={still}
            onNext={next} onClose={close} />
        )}
      </AnimatePresence>
    </div>
  );
}

export default Announcer;
