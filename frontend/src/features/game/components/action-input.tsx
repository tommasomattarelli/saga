import { useState, useRef, useEffect, useCallback } from "react";
import { useGameStore } from "../../../shared/stores/game-store";

interface ActionInputProps {
  campaignId: string;
  onAction: (action: string) => void;
}

const ROTATING_PLACEHOLDERS = [
  "I draw my sword and step forward…",
  "I search the chamber carefully…",
  "I speak softly to the stranger…",
  "I examine the ancient inscription…",
  "I attempt to pick the lock…",
  "I call out into the darkness…",
  "I offer the merchant my gold…",
  "I sneak along the shadowed wall…",
];

export default function ActionInput({ onAction }: ActionInputProps) {
  const [action, setAction] = useState("");
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isLoading = useGameStore((s) => s.isLoading);
  const lastTurn = useGameStore((s) => s.turnHistory[s.turnHistory.length - 1]);

  const showContinue = lastTurn && !lastTurn.requires_player_action;

  // Rotate placeholder every 4s
  useEffect(() => {
    const id = setInterval(() => {
      setPlaceholderIdx((i) => (i + 1) % ROTATING_PLACEHOLDERS.length);
    }, 4000);
    return () => clearInterval(id);
  }, []);

  // Auto-grow textarea up to 6 rows
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const lineHeight = parseInt(getComputedStyle(el).lineHeight, 10) || 28;
    const maxHeight = lineHeight * 6;
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, [action]);

  const sendAction = useCallback(
    (text: string) => {
      if (isLoading) return;
      onAction(text);
      setAction("");
    },
    [isLoading, onAction],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!action.trim()) return;
    sendAction(action.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (action.trim()) sendAction(action.trim());
    }
  };

  return (
    <div
      className="px-6 py-4"
      style={{
        background: "var(--parchment-aged)",
        borderTop: "1px solid var(--gold-deep)",
      }}
    >
      {/* Suggested action pills — "Possibilities:" label */}
      {lastTurn?.suggested_actions && lastTurn.suggested_actions.length > 0 && (
        <div className="mb-3">
          <span
            className="block mb-1.5 font-display text-[9px] uppercase"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.25em" }}
          >
            Possibilities:
          </span>
          <div className="flex flex-wrap gap-2">
            {lastTurn.suggested_actions.map((suggestion, i) => (
              <button
                key={i}
                onClick={() => sendAction(suggestion)}
                disabled={isLoading}
                className="px-3 py-1 font-body text-sm italic transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
                style={{
                  color: "var(--ink-secondary)",
                  border: "1px solid var(--gold-deep)",
                  background: "rgba(244, 232, 208, 0.4)",
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Cartiglio rituale — OrnateFrame-styled container */}
      <form onSubmit={handleSubmit}>
        <div
          className="relative mx-auto max-w-[65ch]"
          style={{
            border: "1px solid var(--gold-deep)",
            outline: "1px solid rgba(184, 134, 11, 0.2)",
            outlineOffset: "3px",
            background: "var(--parchment-base)",
          }}
        >
          {/* Label floating inside top-left */}
          <span
            className="absolute -top-2.5 left-3 px-1 font-display text-[9px] uppercase"
            style={{
              color: "var(--ink-faded)",
              letterSpacing: "0.28em",
              background: "var(--parchment-aged)",
            }}
          >
            What dost thou do?
          </span>

          <textarea
            ref={textareaRef}
            value={action}
            onChange={(e) => setAction(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={ROTATING_PLACEHOLDERS[placeholderIdx]}
            disabled={isLoading}
            rows={1}
            autoFocus
            className="w-full resize-none bg-transparent px-5 pt-4 pb-12 font-body text-lg italic placeholder:opacity-40 focus:outline-none disabled:opacity-50"
            style={{
              color: "var(--ink-primary)",
              lineHeight: "1.7",
              maxHeight: "calc(1.7em * 6 + 2rem)",
              overflow: "hidden",
            }}
          />

          {/* Bottom bar: shortcut hint + submit */}
          <div
            className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-4 py-2"
            style={{ borderTop: "1px solid rgba(139, 105, 20, 0.2)" }}
          >
            <span
              className="font-display text-[9px] uppercase"
              style={{ color: "var(--ink-faded)", letterSpacing: "0.2em", opacity: 0.7 }}
            >
              Ctrl+↵ to seal
            </span>

            {showContinue && !action.trim() ? (
              <button
                type="button"
                onClick={() => sendAction("wait")}
                disabled={isLoading}
                className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
                style={{
                  color: "var(--gold-bright)",
                  border: "1px solid var(--gold-deep)",
                }}
              >
                Continue
              </button>
            ) : (
              <button
                type="submit"
                disabled={isLoading || !action.trim()}
                className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright active:scale-95"
                style={{
                  color: "var(--gold-bright)",
                  border: "1px solid var(--gold-bright)",
                  outline: "1px solid var(--gold-deep)",
                  outlineOffset: "2px",
                  background: "rgba(212, 175, 55, 0.1)",
                }}
              >
                {isLoading ? "…" : "Seal"}
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
