import { useState, useCallback, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import type { DiceRollResult, DiceOutcome } from "../../../shared/types";
import { useUIStore } from "../../../shared/stores/ui-store";

interface DiceRollerProps {
  rolls: Record<string, DiceRollResult>;
  alwaysRevealed?: boolean;
  onAllRevealed?: (step: number) => void;
  step?: number;
}

const OUTCOME_LABELS: Record<DiceOutcome, string> = {
  critical_failure: "CRITICAL FAIL",
  hard_failure: "FAILURE",
  soft_failure: "NEAR MISS",
  partial_success: "PARTIAL",
  full_success: "SUCCESS",
  critical_success: "CRITICAL!",
};

const COUNTER_DURATION_MS = 1500;
const COUNTER_INTERVAL_MS = 60;

function isCrit(outcome?: DiceOutcome): "success" | "fail" | null {
  if (outcome === "critical_success") return "success";
  if (outcome === "critical_failure") return "fail";
  return null;
}

function SingleDice({
  name,
  result,
  alwaysRevealed = false,
  onReveal,
}: {
  name: string;
  result: DiceRollResult;
  alwaysRevealed?: boolean;
  onReveal?: () => void;
}) {
  const [displayValue, setDisplayValue] = useState<number | null>(
    alwaysRevealed ? result.total : null,
  );
  const [revealed, setRevealed] = useState(alwaysRevealed);
  const [animating, setAnimating] = useState(false);
  const soundEnabled = useUIStore((s) => s.soundEnabled);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const playSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const audio = new Audio("/sounds/dice-roll.mp3");
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } catch {
      /* Sound not available */
    }
  }, [soundEnabled]);

  const handleClick = useCallback(() => {
    if (animating || revealed) return;

    setAnimating(true);
    playSound();

    intervalRef.current = setInterval(() => {
      setDisplayValue(Math.floor(Math.random() * 20) + 1);
    }, COUNTER_INTERVAL_MS);

    timeoutRef.current = setTimeout(() => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setDisplayValue(result.total);
      setRevealed(true);
      setAnimating(false);
      onReveal?.();
    }, COUNTER_DURATION_MS);
  }, [animating, revealed, result.total, playSound, onReveal]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const crit = revealed ? isCrit(result.outcome) : null;

  /* Unrevealed — clickable sigil */
  if (!revealed && !animating) {
    return (
      <button
        onClick={handleClick}
        className="group inline-flex items-center gap-3 px-4 py-2 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
        style={{
          border: "1px solid var(--gold-deep)",
          background: "rgba(212, 175, 55, 0.06)",
        }}
      >
        <span
          className="font-display text-[10px] uppercase"
          style={{ color: "var(--ink-faded)", letterSpacing: "0.2em" }}
        >
          {name}
          <span className="ml-2" style={{ opacity: 0.7 }}>
            DC {result.dc}
          </span>
        </span>
        <span
          className="font-display text-base group-hover:scale-110 transition-transform"
          style={{ color: "var(--gold-bright)" }}
        >
          Roll!
        </span>
      </button>
    );
  }

  const success = result.success;

  return (
    <motion.div
      className="inline-flex items-center gap-3 px-4 py-2"
      style={{
        border: `1px solid ${success ? "var(--gold-bright)" : "var(--blood)"}`,
        background: success ? "rgba(212, 175, 55, 0.1)" : "rgba(139, 0, 0, 0.08)",
      }}
      /* Crit screen-shake */
      animate={crit ? { x: [0, -3, 3, -2, 2, 0], transition: { duration: 0.4 } } : undefined}
    >
      <span
        className="font-display text-[10px] uppercase"
        style={{ color: "var(--ink-faded)", letterSpacing: "0.2em" }}
      >
        {name}
      </span>

      {/* The rolled number */}
      <span
        className="font-display text-2xl font-bold"
        style={{
          color:
            crit === "success"
              ? "var(--gold-bright)"
              : crit === "fail"
                ? "var(--blood)"
                : "var(--ink-primary)",
        }}
      >
        {displayValue}
      </span>

      {revealed && (
        <>
          <span className="font-body text-xs" style={{ color: "var(--ink-faded)" }}>
            [{result.rolls.join(", ")}]
            {result.modifier !== 0 && (
              <>{result.modifier > 0 ? `+${result.modifier}` : result.modifier}</>
            )}{" "}
            vs DC {result.dc}
          </span>
          <span
            className="font-display text-xs uppercase"
            style={{
              color: success ? "var(--gold-bright)" : "var(--blood)",
              letterSpacing: "0.15em",
            }}
          >
            {result.outcome ? OUTCOME_LABELS[result.outcome] : success ? "SUCCESS" : "FAILURE"}
          </span>
        </>
      )}

      {/* Ink-blot splash on crit */}
      {crit && (
        <motion.span
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 0.15 }}
          transition={{ duration: 0.5 }}
          className="absolute -inset-2 pointer-events-none"
          style={{
            borderRadius: "50%",
            background:
              crit === "success"
                ? "radial-gradient(circle, var(--gold-bright), transparent 70%)"
                : "radial-gradient(circle, var(--blood), transparent 70%)",
          }}
        />
      )}
    </motion.div>
  );
}

export default function DiceRoller({
  rolls,
  alwaysRevealed = false,
  onAllRevealed,
  step = 0,
}: DiceRollerProps) {
  const total = Object.keys(rolls).length;
  const [, setRevealedCount] = useState(alwaysRevealed ? total : 0);

  const handleReveal = useCallback(() => {
    setRevealedCount((c) => {
      const next = c + 1;
      if (next >= total) onAllRevealed?.(step);
      return next;
    });
  }, [total, onAllRevealed, step]);

  return (
    <div className="my-4 flex flex-wrap gap-2">
      {Object.entries(rolls).map(([name, result]) => (
        <div key={name} className="relative">
          <SingleDice
            name={name}
            result={result}
            alwaysRevealed={alwaysRevealed}
            onReveal={handleReveal}
          />
        </div>
      ))}
    </div>
  );
}
