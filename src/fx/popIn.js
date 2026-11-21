import { useReducedMotion } from "motion/react";

// The React Bits AnimatedList entrance for lists whose rows hold buttons (AnimatedList makes every
// row a selectable option, which those can't be): rows slide up into place one after another the
// first time the list scrolls into view. Spread `list` on the motion list and `item` on each row.
// With reduced motion on, rows just appear.

const LIST = { hidden: {}, show: { transition: { staggerChildren: 0.05 } } };
const ITEM = {
  hidden: { opacity: 0, y: 28, scale: 0.98 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: "spring", stiffness: 260, damping: 20 } },
};

export function usePopIn() {
  const reduce = useReducedMotion();
  if (reduce) return { list: {}, item: {} };
  return {
    list: { variants: LIST, initial: "hidden", whileInView: "show", viewport: { once: true, amount: 0.15 } },
    item: { variants: ITEM },
  };
}
