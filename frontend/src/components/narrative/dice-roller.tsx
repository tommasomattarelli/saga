import { useState, useEffect, useCallback, useRef } from "react";
import type { DiceRollResult, DiceOutcome } from "../../types";
import { useUIStore } from "../../stores/ui-store";
import { useGameStore } from "../../stores/game-store";

interface DiceRollerProps {
  rolls: Record<string, DiceRollResult>;
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

function SingleDice({ name, result }: { name: string; result: DiceRollResult }) {
  const [displayValue, setDisplayValue] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [animating, setAnimating] = useState(false);
  const soundEnabled = useUIStore((s) => s.soundEnabled);
  const revealDice = useGameStore((s) => s.revealDice);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const playSound = useCallback(() => {
    if (!soundEnabled) return;
    try {
      const audio = new Audio("/sounds/dice-roll.mp3");
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } catch {
      // Sound not available
    }
  }, [soundEnabled]);

  const handleClick = useCallback(() => {
    if (animating || revealed) return;

    setAnimating(true);
    playSound();

    // Counter animation: rapidly cycle 1-20
    intervalRef.current = setInterval(() => {
      setDisplayValue(Math.floor(Math.random() * 20) + 1);
    }, COUNTER_INTERVAL_MS);

    // Stop after duration and reveal real value
    timeoutRef.current = setTimeout(() => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setDisplayValue(result.total);
      setRevealed(true);
      setAnimating(false);
      revealDice();
    }, COUNTER_DURATION_MS);
  }, [animating, revealed, result.total, playSound, revealDice]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const outcomeClass = result.outcome ? `dice-${result.outcome}` : "";

  if (!revealed && !animating) {
    // Waiting for click
    return (
      <button
        onClick={handleClick}
        className="inline-flex items-center gap-3 rounded-lg border border-gold-500/50 bg-parchment-800/50 px-4 py-2 transition hover:border-gold-400 hover:bg-parchment-700/50"
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-parchment-400">
          {name}
          <span className="ml-2 text-parchment-500">DC {result.dc}</span>
        </span>
        <span className="font-display text-lg text-gold-400">Roll!</span>
      </button>
    );
  }

  return (
    <div
      className={`inline-flex items-center gap-3 rounded-lg border px-4 py-2 ${outcomeClass || (result.success ? "border-green-700/50 bg-green-900/20" : "border-red-700/50 bg-red-900/20")}`}
    >
      <span className="text-xs font-semibold uppercase tracking-wider text-parchment-400">
        {name}
      </span>
      <span
        className={`font-display text-2xl font-bold text-parchment-100 ${revealed ? "dice-final" : "dice-counter-animate"}`}
      >
        {displayValue}
      </span>
      {revealed && (
        <>
          <span className="text-xs text-parchment-500">
            [{result.rolls.join(", ")}]
            {result.modifier !== 0 && (
              <>{result.modifier > 0 ? `+${result.modifier}` : result.modifier}</>
            )}{" "}
            vs DC {result.dc}
          </span>
          <span
            className={`text-sm font-bold ${result.success ? "text-green-400" : "text-red-400"}`}
          >
            {result.outcome
              ? OUTCOME_LABELS[result.outcome]
              : result.success
                ? "SUCCESS"
                : "FAILURE"}
          </span>
        </>
      )}
    </div>
  );
}

export default function DiceRoller({ rolls }: DiceRollerProps) {
  return (
    <div className="mb-4 space-y-2">
      {Object.entries(rolls).map(([name, result]) => (
        <SingleDice key={name} name={name} result={result} />
      ))}
    </div>
  );
}
