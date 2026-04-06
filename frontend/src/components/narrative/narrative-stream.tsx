import { type RefObject, useEffect } from "react";
import { useGameStore } from "../../stores/game-store";
import DiceRoller from "./dice-roller";
import type { TurnResponse } from "../../types";
import type { GameWebSocket } from "../../services/websocket";

function PlayerBubble({ action }: { action: string }) {
  return (
    <div className="mb-4 flex justify-end">
      <div className="max-w-[80%] rounded-lg border border-gold-500/20 bg-gold-900/30 px-4 py-2">
        <p className="text-sm font-serif text-gold-300">{action}</p>
      </div>
    </div>
  );
}

interface NarrativeStreamProps {
  wsRef: RefObject<GameWebSocket | null>;
  scrollRef?: RefObject<HTMLDivElement | null>;
}

function TurnBlock({
  turn,
  onSuggestedAction,
}: {
  turn: TurnResponse;
  onSuggestedAction?: (action: string) => void;
}) {
  return (
    <div className="mb-6" data-mood={turn.scene_mood || "neutral"}>
      {turn.player_action && <PlayerBubble action={turn.player_action} />}

      <div className="prose prose-invert max-w-none font-serif leading-relaxed mood-text">
        {turn.narration.split("\n").map((paragraph, i) => (
          <p key={i} className="mb-3">
            {paragraph}
          </p>
        ))}
      </div>

      {turn.dice_rolls && <DiceRoller rolls={turn.dice_rolls} />}

      {turn.ambient_detail && (
        <p className="mt-2 text-sm italic text-parchment-500">{turn.ambient_detail}</p>
      )}

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
              onClick={() => onSuggestedAction?.(action)}
              className="rounded-full border border-parchment-600/30 bg-parchment-800/50 px-3 py-1 text-sm text-parchment-300 transition hover:border-gold-500/50 hover:text-gold-400"
            >
              {action}
            </button>
          ))}
        </div>
      )}

      {turn.scene_mood && turn.scene_mood !== "neutral" && (
        <div className="mood-accent mt-2 text-xs uppercase tracking-wider">
          {turn.scene_mood.replace("_", " ")}
        </div>
      )}
    </div>
  );
}

export default function NarrativeStream({ wsRef, scrollRef }: NarrativeStreamProps) {
  const turnHistory = useGameStore((s) => s.turnHistory);
  const isProcessing = useGameStore((s) => s.isProcessing);
  const streaming = useGameStore((s) => s.streaming);

  const handleSuggestedAction = (action: string) => {
    wsRef.current?.send({ action });
  };

  useEffect(() => {
    const el = scrollRef?.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [streaming.currentNarration, turnHistory.length, scrollRef]);

  return (
    <div>
      {turnHistory.length === 0 && !isProcessing && !streaming.pendingAction && (
        <div className="py-12 text-center">
          <p className="font-display text-xl text-gold-400">Your adventure awaits...</p>
          <p className="mt-2 text-sm text-parchment-500">Type an action below to begin</p>
        </div>
      )}

      {turnHistory.map((turn, i) => (
        <TurnBlock key={i} turn={turn} onSuggestedAction={handleSuggestedAction} />
      ))}

      {/* Pending player action bubble */}
      {streaming.pendingAction && <PlayerBubble action={streaming.pendingAction} />}

      {/* Live streaming narration */}
      {streaming.isStreaming && streaming.currentNarration && (
        <div className="mb-6">
          <div className="prose prose-invert max-w-none font-serif leading-relaxed mood-text">
            {streaming.currentNarration.split("\n").map((paragraph, i) => (
              <p key={i} className="mb-3">
                {paragraph}
              </p>
            ))}
          </div>
          {streaming.pendingDice && <DiceRoller rolls={streaming.pendingDice} />}
        </div>
      )}

      {isProcessing && !streaming.currentNarration && (
        <div className="flex items-center gap-2 py-4 text-parchment-400">
          <span className="text-sm">The DM considers your action</span>
          <span className="flex gap-1">
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-gold-400" />
          </span>
        </div>
      )}

      <div />
    </div>
  );
}
