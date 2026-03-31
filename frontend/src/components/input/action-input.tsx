import { useState, type RefObject } from "react";
import { useGameStore } from "../../stores/game-store";
import type { GameWebSocket } from "../../services/websocket";

interface ActionInputProps {
  campaignId: string;
  wsRef: RefObject<GameWebSocket | null>;
}

export default function ActionInput({ wsRef }: ActionInputProps) {
  const [action, setAction] = useState("");
  const { isProcessing, turnHistory, setPendingAction } = useGameStore();

  const lastTurn = turnHistory[turnHistory.length - 1];
  const showContinue = lastTurn && !lastTurn.requires_player_action;

  const sendAction = (text: string) => {
    if (isProcessing) return;
    setPendingAction(text);
    wsRef.current?.send({ action: text });
    setAction("");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!action.trim()) return;
    sendAction(action.trim());
  };

  const handleContinue = () => {
    sendAction("wait");
  };

  const handleSuggestion = (suggestion: string) => {
    sendAction(suggestion);
  };

  return (
    <div className="border-t border-parchment-700/20 bg-parchment-900/95 px-6 py-4">
      {/* Suggested actions from last turn */}
      {lastTurn?.suggested_actions && lastTurn.suggested_actions.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {lastTurn.suggested_actions.map((suggestion, i) => (
            <button
              key={i}
              onClick={() => handleSuggestion(suggestion)}
              disabled={isProcessing}
              className="rounded-full border border-parchment-600/30 bg-parchment-800/50 px-3 py-1 text-sm text-parchment-300 transition hover:border-gold-500/50 hover:text-gold-400 disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="What do you do?"
          disabled={isProcessing}
          className="flex-1 rounded-lg border border-parchment-700/30 bg-parchment-800/50 px-4 py-3 font-serif text-parchment-100 placeholder-parchment-600 focus:border-gold-500/50 focus:outline-none disabled:opacity-50"
          autoFocus
        />
        {showContinue && !action.trim() ? (
          <button
            type="button"
            onClick={handleContinue}
            disabled={isProcessing}
            className="rounded-lg border border-gold-500/50 bg-parchment-800 px-6 py-3 font-display font-semibold text-gold-400 transition hover:bg-parchment-700 disabled:opacity-50"
          >
            Continue
          </button>
        ) : (
          <button
            type="submit"
            disabled={isProcessing || !action.trim()}
            className="rounded-lg bg-gold-500 px-6 py-3 font-display font-semibold text-parchment-900 transition hover:bg-gold-400 disabled:opacity-50"
          >
            Act
          </button>
        )}
      </form>
    </div>
  );
}
