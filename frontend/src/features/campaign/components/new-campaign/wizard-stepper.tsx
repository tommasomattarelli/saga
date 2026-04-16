/* 3-sigil stepper for the new-campaign ritual */

interface WizardStepperProps {
  step: 1 | 2 | 3;
}

const GLYPHS: Array<{ glyph: string; label: string }> = [
  { glyph: "✷", label: "The World" },
  { glyph: "❖", label: "The Hero" },
  { glyph: "⚔", label: "The Fate" },
];

export function WizardStepper({ step }: WizardStepperProps) {
  return (
    <div className="flex items-center justify-center gap-4 mb-8" aria-label={`Step ${step} of 3`}>
      {GLYPHS.map((item, i) => {
        const n = (i + 1) as 1 | 2 | 3;
        const isActive = n === step;
        const isDone = n < step;
        return (
          <div key={i} className="flex items-center gap-4">
            <div className="flex flex-col items-center gap-1">
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center transition-all"
                style={{
                  border: `1px solid ${isActive || isDone ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                  background: isActive ? "rgba(212, 175, 55, 0.12)" : "transparent",
                  opacity: isActive ? 1 : isDone ? 0.85 : 0.45,
                  boxShadow: isActive ? "0 0 16px rgba(212,175,55,0.35)" : "none",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: 22,
                    color: isActive ? "var(--gold-bright)" : "var(--gold-deep)",
                  }}
                >
                  {item.glyph}
                </span>
              </div>
              <span
                className="font-display text-[9px] uppercase"
                style={{
                  letterSpacing: "0.22em",
                  color: isActive ? "var(--gold-bright)" : "var(--ink-faded)",
                  opacity: isActive ? 1 : 0.75,
                }}
              >
                {item.label}
              </span>
            </div>

            {/* Connecting line */}
            {i < GLYPHS.length - 1 && (
              <div
                aria-hidden="true"
                className="w-16 h-px"
                style={{
                  background: "var(--gold-deep)",
                  opacity: isDone ? 0.85 : 0.35,
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
