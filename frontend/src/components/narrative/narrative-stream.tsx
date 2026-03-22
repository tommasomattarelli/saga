import { useGameStore } from "../../stores/game-store";
import DiceRoller from "./dice-roller";
import type { TurnResponse } from "../../types";

function TurnBlock({ turn }: { turn: TurnResponse }) {
  return (
    <div className="mb-6">
      {turn.dice_rolls && <DiceRoller rolls={turn.dice_rolls} />}

      <div className="prose prose-invert max-w-none font-serif text-parchment-200 leading-relaxed">
        {turn.narration.split("\n").map((paragraph, i) => (
          <p key={i} className="mb-3">
            {paragraph}
          </p>
        ))}
      </div>

      {turn.companion_actions && (
        <div className="mt-3 space-y-1">
          {Object.entries(turn.companion_actions).map(([name, action]) => (
            <p key={name} className="text-sm italic text-parchment-400">
              <span className="font-semibold text-parchment-300">{name}</span> {action}
            </p>
          ))}
        </div>
      )}

      {turn.suggested_actions && turn.suggested_actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {turn.suggested_actions.map((action, i) => (
            <button
              key={i}
              className="rounded-full border border-parchment-600/30 bg-parchment-800/50 px-3 py-1 text-sm text-parchment-300 transition hover:border-gold-500/50 hover:text-gold-400"
            >
              {action}
            </button>
          ))}
        </div>
      )}

      {turn.scene_mood && (
        <div className="mt-2 text-xs uppercase tracking-wider text-parchment-600">
          {turn.scene_mood}
        </div>
      )}
    </div>
  );
}

export default function NarrativeStream() {
  const turnHistory = useGameStore((s) => s.turnHistory);
  const isProcessing = useGameStore((s) => s.isProcessing);

  return (
    <div>
      {turnHistory.length === 0 && !isProcessing && (
        <div className="py-12 text-center">
          <p className="font-display text-xl text-gold-400">Your adventure awaits...</p>
          <p className="mt-2 text-sm text-parchment-500">Type an action below to begin</p>
        </div>
      )}

      {turnHistory.map((turn, i) => (
        <TurnBlock key={i} turn={turn} />
      ))}

      {isProcessing && (
        <div className="flex items-center gap-2 py-4 text-parchment-400">
          <span className="text-sm">The DM considers your action</span>
          <span className="flex gap-1">
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
          </span>
        </div>
      )}
    </div>
  );
}
