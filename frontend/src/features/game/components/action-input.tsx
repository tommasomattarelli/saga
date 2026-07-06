import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";

interface ActionInputProps {
  onAction: (action: string) => Promise<void>;
}

// ponytail: backend sanitize_player_input is the real guard; this is just UX feedback
const MAX_ACTION_LENGTH = 500;

export default function ActionInput({ onAction }: ActionInputProps) {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isLoading = useGameStore((s) => s.isLoading);
  const hasPendingDice = useGameStore((s) => s.hasPendingDice);
  const lastTurn = useGameStore((s) => s.turnHistory[s.turnHistory.length - 1]);

  const showContinue = lastTurn && !lastTurn.requires_player_action;

  // Auto-grow textarea up to 6 rows
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 28;
    const maxHeight = lineHeight * 6;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, [action]);

  const blocked = isLoading || hasPendingDice;

  const sendAction = useCallback(
    async (text: string) => {
      if (blocked) return;
      setAction("");
      try {
        await onAction(text);
      } catch {
        setAction(text); // failed submit — give the player their words back
      }
    },
    [blocked, onAction],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!action.trim()) return;
    void sendAction(action.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (action.trim()) void sendAction(action.trim());
    }
  };

  return (
    <div
      className="px-6 py-4"
      style={{
        background: "var(--parchment-aged)",
        borderTop: "1px solid var(--line)",
      }}
    >
      <form onSubmit={handleSubmit} className="mx-auto" style={{ maxWidth: "68ch" }}>
        <div
          className="rounded-2xl px-5 py-3"
          style={{
            border: "1px solid var(--line-strong)",
            background: "var(--parchment-base)",
          }}
        >
          <textarea
            ref={textareaRef}
            value={action}
            onChange={(e) => setAction(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t("game.action_placeholder")}
            aria-label={t("game.action_placeholder")}
            disabled={blocked}
            maxLength={MAX_ACTION_LENGTH}
            rows={1}
            autoFocus
            className="w-full resize-none bg-transparent font-body text-lg placeholder:italic focus:outline-none disabled:opacity-50"
            style={{
              color: "var(--ink-primary)",
              lineHeight: "1.6",
              maxHeight: "calc(1.6em * 6)",
              overflowY: "auto",
            }}
          />

          <div className="mt-2 flex items-center justify-between">
            <div className="flex items-center gap-3 font-display text-[11px]">
              <span style={{ color: "var(--ink-faded)" }}>
                {hasPendingDice ? t("game.reveal_dice") : t("game.input_hint")}
              </span>
              {action.length > MAX_ACTION_LENGTH - 50 && (
                <span
                  aria-live="polite"
                  style={{
                    color: action.length >= MAX_ACTION_LENGTH ? "var(--blood)" : "var(--ink-faded)",
                  }}
                >
                  {action.length}/{MAX_ACTION_LENGTH}
                </span>
              )}
            </div>

            {showContinue && !action.trim() ? (
              <button
                type="button"
                onClick={() => void sendAction("wait")}
                disabled={blocked}
                className="rounded-full px-4 py-1 font-display text-[13px] transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                style={{
                  color: "var(--ink-secondary)",
                  border: "1px solid var(--line-strong)",
                }}
              >
                {t("game.continue")}
              </button>
            ) : (
              <button
                type="submit"
                disabled={blocked || !action.trim()}
                className="font-display text-[13px] font-semibold transition disabled:opacity-40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                style={{ color: "var(--accent)" }}
              >
                {isLoading ? "…" : `${t("game.send")} ↵`}
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
