import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

const DM_STATES = [
  "The chronicler dips quill in ink…",
  "The DM consults ancient tomes…",
  "Fate deliberates thy doom…",
  "The threads of destiny weave…",
  "A quill scratches upon parchment…",
  "The oracle peers into the abyss…",
  "Stars align above the realm…",
  "The Weave shimmers with intent…",
];

function pickState(exclude: number): number {
  let next: number;
  do {
    next = Math.floor(Math.random() * DM_STATES.length);
  } while (next === exclude && DM_STATES.length > 1);
  return next;
}

export default function DmLoading() {
  const [stateIdx, setStateIdx] = useState(() => Math.floor(Math.random() * DM_STATES.length));

  useEffect(() => {
    const interval = setInterval(() => {
      setStateIdx((prev) => pickState(prev));
    }, 3200);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="mb-6 py-6 text-center" data-testid="dm-loading">
      {/* Quill dots */}
      <div className="flex items-center justify-center gap-1.5 mb-3">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="block rounded-full"
            style={{
              width: 6,
              height: 6,
              background: "var(--gold-bright)",
            }}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.3,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>

      {/* Rotating flavour text */}
      <AnimatePresence mode="wait">
        <motion.p
          key={stateIdx}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.4 }}
          className="font-body italic text-sm"
          style={{ color: "var(--ink-faded)" }}
        >
          {DM_STATES[stateIdx]}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
