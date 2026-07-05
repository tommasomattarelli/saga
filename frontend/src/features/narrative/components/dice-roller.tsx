import { useState, useCallback, useRef, useEffect } from "react";
import type { DiceRollResult, DiceOutcome } from "../../../shared/types";
import { useUIStore } from "../../../shared/stores/ui-store";

interface DiceRollerProps {
  rolls: Record<string, DiceRollResult>;
  alwaysRevealed?: boolean;
  onAllRevealed?: (step: number) => void;
  step?: number;
}

/* The six outcome tiers, worst → best; the arc renders them in this order */
const TIER_ORDER: DiceOutcome[] = [
  "critical_failure",
  "hard_failure",
  "soft_failure",
  "partial_success",
  "full_success",
  "critical_success",
];

const OUTCOME_LABELS: Record<DiceOutcome, string> = {
  critical_failure: "Critical fail",
  hard_failure: "Failure",
  soft_failure: "Near miss",
  partial_success: "Partial success",
  full_success: "Success",
  critical_success: "Critical success",
};

const SWEEP_DURATION_MS = 1100;
const SWEEP_INTERVAL_MS = 90;

function outcomeOf(result: DiceRollResult): DiceOutcome {
  return result.outcome ?? (result.success ? "full_success" : "hard_failure");
}

/* Tier arc — all six outcomes visible as segments; the marker lands on the rolled tier */
function TierArc({
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
  const [revealed, setRevealed] = useState(alwaysRevealed);
  const [sweepIdx, setSweepIdx] = useState<number | null>(null);
  const soundEnabled = useUIStore((s) => s.soundEnabled);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const outcome = outcomeOf(result);
  const tierIdx = TIER_ORDER.indexOf(outcome);
  const isCrit = outcome === "critical_failure" || outcome === "critical_success";
  const hitColor = result.success ? "var(--accent)" : "var(--blood)";

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
    if (revealed || sweepIdx !== null) return;
    playSound();

    let idx = 0;
    setSweepIdx(0);
    intervalRef.current = setInterval(() => {
      idx = (idx + 1) % TIER_ORDER.length;
      setSweepIdx(idx);
    }, SWEEP_INTERVAL_MS);

    timeoutRef.current = setTimeout(() => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      setSweepIdx(null);
      setRevealed(true);
      onReveal?.();
    }, SWEEP_DURATION_MS);
  }, [revealed, sweepIdx, playSound, onReveal]);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  /* Unrevealed — quiet clickable row */
  if (!revealed && sweepIdx === null) {
    return (
      <button
        onClick={handleClick}
        className="flex w-full items-center justify-between rounded-lg px-4 py-2.5 transition focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        style={{ border: "1px solid var(--line-strong)" }}
      >
        <span
          className="font-display text-[11px] uppercase"
          style={{ color: "var(--ink-faded)", letterSpacing: "0.12em" }}
        >
          {name} · DC {result.dc}
        </span>
        <span className="font-display text-[13px] font-semibold" style={{ color: "var(--accent)" }}>
          Roll
        </span>
      </button>
    );
  }

  const modifier =
    result.modifier !== 0 ? ` ${result.modifier > 0 ? "+" : "−"} ${Math.abs(result.modifier)}` : "";

  return (
    <div
      className="py-3"
      style={{ borderTop: "1px solid var(--line)", borderBottom: "1px solid var(--line)" }}
    >
      <div
        className="mb-2.5 flex items-center justify-between font-display text-[11px] uppercase"
        style={{ color: "var(--ink-faded)", letterSpacing: "0.12em" }}
      >
        <span>{name}</span>
        <span>DC {result.dc}</span>
      </div>

      {/* The six tiers; the landed one rises in the outcome color */}
      <div className="flex items-center gap-1" style={{ height: 10 }} aria-hidden="true">
        {TIER_ORDER.map((tier, i) => {
          const isHit = revealed && i === tierIdx;
          const isSweep = !revealed && i === sweepIdx;
          return (
            <span
              key={tier}
              className="flex-1 rounded-sm transition-all duration-100"
              style={{
                height: isHit || isSweep ? 9 : 3,
                background: isHit ? hitColor : isSweep ? "var(--ink-faded)" : "var(--line-strong)",
              }}
            />
          );
        })}
      </div>

      {revealed && (
        <p className="mt-2.5 font-display text-[13px]" style={{ color: "var(--ink-secondary)" }}>
          <span style={{ color: "var(--ink-faded)" }}>
            {result.rolls.join(" + ")}
            {modifier} ={" "}
          </span>
          <span style={{ color: "var(--ink-primary)" }}>{result.total}</span>
          <span style={{ color: "var(--ink-faded)" }}> — </span>
          <span
            className={isCrit ? "uppercase font-semibold" : "font-semibold"}
            style={{ color: hitColor, letterSpacing: isCrit ? "0.06em" : undefined }}
          >
            {OUTCOME_LABELS[outcome]}
          </span>
        </p>
      )}
    </div>
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
    <div className="my-5 space-y-2" style={{ maxWidth: "26rem" }}>
      {Object.entries(rolls).map(([name, result]) => (
        <TierArc
          key={name}
          name={name}
          result={result}
          alwaysRevealed={alwaysRevealed}
          onReveal={handleReveal}
        />
      ))}
    </div>
  );
}
