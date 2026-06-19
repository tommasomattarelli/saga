import { useLayoutEffect, useCallback } from "react";
import { useGameStore } from "../../../shared/stores/game-store";
import DmLoading from "./dm-loading";
import PlayerAction from "./player-action";
import TurnBlock from "./turn-block";

export default function NarrativeStream({
  scrollRef,
  actionError,
}: {
  scrollRef?: React.RefObject<HTMLDivElement | null>;
  actionError?: string | null;
}) {
  const turnHistory = useGameStore((s) => s.turnHistory);
  const isLoading = useGameStore((s) => s.isLoading);
  const pendingAction = useGameStore((s) => s.pendingAction);
  const freshTurnNumber = useGameStore((s) => s.freshTurnNumber);
  const clearPendingDice = useGameStore((s) => s.clearPendingDice);

  const handleDiceAllRevealed = useCallback(() => {
    clearPendingDice();
  }, [clearPendingDice]);

  useLayoutEffect(() => {
    const el = scrollRef?.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turnHistory.length, isLoading, scrollRef]);

  return (
    <div aria-live="polite" aria-label="Narrative">
      {turnHistory.length === 0 && !isLoading && !pendingAction && (
        <div className="py-16 text-center">
          <p
            className="font-display text-xl uppercase"
            style={{ color: "var(--gold-bright)", letterSpacing: "0.25em" }}
          >
            Thy adventure awaits…
          </p>
          <p className="mt-3 font-body italic text-sm" style={{ color: "var(--ink-faded)" }}>
            Inscribe thine action below to begin
          </p>
        </div>
      )}

      {turnHistory.map((turn, i) => {
        const isLatest = i === turnHistory.length - 1;
        return (
          <TurnBlock
            key={turn.turn_number}
            turn={turn}
            isLatest={isLatest}
            isFresh={turn.turn_number === freshTurnNumber}
            isFirst={i === 0}
            showDivider={i > 0}
            onAllDiceRevealed={isLatest ? handleDiceAllRevealed : undefined}
          />
        );
      })}

      {pendingAction && isLoading && <PlayerAction action={pendingAction} />}

      {isLoading && <DmLoading />}

      {actionError && !isLoading && (
        <div
          className="mb-4 p-3 font-body text-sm italic"
          style={{
            border: "1px solid var(--blood)",
            background: "rgba(139, 0, 0, 0.08)",
            color: "var(--blood)",
          }}
        >
          ❧ {actionError}
        </div>
      )}
    </div>
  );
}
