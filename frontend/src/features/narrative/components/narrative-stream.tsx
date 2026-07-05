import { useLayoutEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
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
        <div className="py-24 text-center">
          <p className="font-display text-lg font-semibold" style={{ color: "var(--ink-primary)" }}>
            {t("game.empty_title")}
          </p>
          <p className="mt-2 font-body italic text-base" style={{ color: "var(--ink-faded)" }}>
            {t("game.empty_hint")}
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
          role="alert"
          className="mb-4 rounded-md px-4 py-3 font-display text-sm"
          style={{
            border: "1px solid var(--blood-dark)",
            color: "var(--blood)",
          }}
        >
          {actionError}
        </div>
      )}
    </div>
  );
}
