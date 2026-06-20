import { useState, useRef, useEffect, useCallback } from "react";
import { useGameStore } from "../../../shared/stores/game-store";

interface ActionInputProps {
  onAction: (action: string) => void;
}

// ponytail: backend sanitize_player_input is the real guard; this is just UX feedback
const MAX_ACTION_LENGTH = 500;

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
  const hasPendingDice = useGameStore((s) => s.hasPendingDice);
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

  const blocked = isLoading || hasPendingDice;

  const sendAction = useCallback(
    (text: string) => {
      if (blocked) return;
      onAction(text);
      setAction("");
    },
    [blocked, onAction],
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
            disabled={blocked}
            maxLength={MAX_ACTION_LENGTH}
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
            <div className="flex items-center gap-3">
              <span
                className="font-display text-[9px] uppercase"
                style={{ color: "var(--ink-faded)", letterSpacing: "0.2em", opacity: 0.7 }}
              >
                Ctrl+↵ to seal
              </span>
              {action.length > MAX_ACTION_LENGTH - 50 && (
                <span
                  aria-live="polite"
                  className="font-display text-[9px]"
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
                onClick={() => sendAction("wait")}
                disabled={blocked}
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
                disabled={blocked || !action.trim()}
                className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-1 transition disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright active:scale-95"
                style={{
                  color: "var(--gold-bright)",
                  border: "1px solid var(--gold-bright)",
                  outline: "1px solid var(--gold-deep)",
                  outlineOffset: "2px",
                  background: "rgba(212, 175, 55, 0.1)",
                }}
              >
                {isLoading ? "…" : hasPendingDice ? "Cast the die…" : "Seal"}
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
