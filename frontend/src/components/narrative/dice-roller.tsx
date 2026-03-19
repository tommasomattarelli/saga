import type { DiceRollResult } from "../../types";

interface DiceRollerProps {
  rolls: Record<string, DiceRollResult>;
}

export default function DiceRoller({ rolls }: DiceRollerProps) {
  return (
    <div className="mb-4 space-y-2">
      {Object.entries(rolls).map(([name, result]) => (
        <div
          key={name}
          className={`inline-flex items-center gap-3 rounded-lg border px-4 py-2 ${
            result.success
              ? "border-green-700/50 bg-green-900/20"
              : "border-red-700/50 bg-red-900/20"
          }`}
        >
          <span className="text-xs font-semibold uppercase tracking-wider text-parchment-400">
            {name}
          </span>
          <span className="animate-dice-roll font-display text-2xl font-bold text-parchment-100">
            {result.total}
          </span>
          <span className="text-xs text-parchment-500">
            [{result.rolls.join(", ")}] vs DC {result.dc}
          </span>
          <span
            className={`text-sm font-bold ${result.success ? "text-green-400" : "text-red-400"}`}
          >
            {result.success ? "SUCCESS" : "FAILURE"}
          </span>
        </div>
      ))}
    </div>
  );
}
