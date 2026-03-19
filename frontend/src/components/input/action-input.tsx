import { useState } from "react";
import { submitTurn } from "../../services/api";
import { useGameStore } from "../../stores/game-store";

interface ActionInputProps {
  campaignId: string;
}

export default function ActionInput({ campaignId }: ActionInputProps) {
  const [action, setAction] = useState("");
  const { addTurn, setProcessing, isProcessing } = useGameStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!action.trim() || isProcessing) return;

    const playerAction = action.trim();
    setAction("");
    setProcessing(true);

    try {
      const { data: turn } = await submitTurn(campaignId, playerAction);
      addTurn(turn);
    } catch (err) {
      console.error("Turn submission failed:", err);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-parchment-700/20 bg-parchment-900/95 px-6 py-4"
    >
      <div className="flex gap-3">
        <input
          type="text"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder="What do you do?"
          disabled={isProcessing}
          className="flex-1 rounded-lg border border-parchment-700/30 bg-parchment-800/50 px-4 py-3 font-serif text-parchment-100 placeholder-parchment-600 focus:border-gold-500/50 focus:outline-none disabled:opacity-50"
          autoFocus
        />
        <button
          type="submit"
          disabled={isProcessing || !action.trim()}
          className="rounded-lg bg-gold-500 px-6 py-3 font-display font-semibold text-parchment-900 transition hover:bg-gold-400 disabled:opacity-50"
        >
          Act
        </button>
      </div>
    </form>
  );
}
