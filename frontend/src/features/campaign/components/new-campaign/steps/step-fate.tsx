import { motion } from "framer-motion";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { DEATH_MODES } from "../../../data/class-presets";

interface FateForm {
  heroName: string;
  campaignName: string;
  deathMode: string;
  background: string;
}

interface Props {
  form: FateForm;
  onChange: (patch: Partial<FateForm>) => void;
  onBack: () => void;
  onSubmit: () => void;
  isPending: boolean;
  error: string | null;
}

const DEATH_GLYPHS: Record<string, string> = {
  cronista: "❦",
  destino: "☉",
  ironman: "☠",
};

export default function StepFate({ form, onChange, onBack, onSubmit, isPending, error }: Props) {
  return (
    <div>
      <div className="mb-6 text-center">
        <h2
          className="font-display text-2xl uppercase"
          style={{ color: "var(--gold-bright)", letterSpacing: "0.22em" }}
        >
          The Fate
        </h2>
        <p
          className="mt-2 font-body italic text-sm"
          style={{ color: "var(--ink-secondary)" }}
        >
          Title thy tale and decree the weight of death upon it.
        </p>
      </div>

      <div className="space-y-6">
        {/* Campaign name */}
        <div>
          <label
            htmlFor="campaign-name"
            className="block mb-2 font-display text-[10px] uppercase"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
          >
            Title of the Saga
          </label>
          <input
            id="campaign-name"
            type="text"
            value={form.campaignName}
            onChange={(e) => onChange({ campaignName: e.target.value })}
            placeholder={`${form.heroName || "The Stranger"}'s Adventure`}
            className="w-full bg-transparent py-2 font-body text-lg italic focus:outline-none"
            style={{
              color: "var(--ink-primary)",
              borderBottom: "1px solid var(--gold-deep)",
            }}
          />
        </div>

        {/* Background */}
        <div>
          <label
            htmlFor="background"
            className="block mb-2 font-display text-[10px] uppercase"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
          >
            Origin <span style={{ opacity: 0.6 }}>— optional</span>
          </label>
          <input
            id="background"
            type="text"
            value={form.background}
            onChange={(e) => onChange({ background: e.target.value })}
            placeholder="A wandering sellsword seeking redemption…"
            className="w-full bg-transparent py-2 font-body text-base italic focus:outline-none"
            style={{
              color: "var(--ink-primary)",
              borderBottom: "1px solid var(--gold-deep)",
            }}
          />
        </div>

        {/* Death mode sigils */}
        <div>
          <label
            className="block mb-3 font-display text-[10px] uppercase"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
          >
            Decree of Death
          </label>
          <RadioGroup.Root
            value={form.deathMode}
            onValueChange={(v) => onChange({ deathMode: v })}
            className="grid grid-cols-1 sm:grid-cols-3 gap-3"
          >
            {DEATH_MODES.map((m) => {
              const selected = form.deathMode === m.value;
              const glyph = DEATH_GLYPHS[m.value] ?? "✦";
              return (
                <RadioGroup.Item
                  key={m.value}
                  value={m.value}
                  asChild
                >
                  <motion.button
                    whileHover={{ y: -2 }}
                    transition={{ type: "spring", stiffness: 300, damping: 22 }}
                    className="relative p-4 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
                    style={{
                      border: `1px solid ${selected ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                      background: selected
                        ? "rgba(212, 175, 55, 0.12)"
                        : "rgba(244, 232, 208, 0.04)",
                      boxShadow: selected ? "0 0 18px rgba(212,175,55,0.3)" : "none",
                    }}
                  >
                    <div
                      className="font-display mb-1"
                      style={{
                        fontSize: 28,
                        color: selected ? "var(--gold-bright)" : "var(--gold-deep)",
                      }}
                    >
                      {glyph}
                    </div>
                    <div
                      className="font-display text-sm uppercase"
                      style={{
                        color: selected ? "var(--gold-bright)" : "var(--ink-secondary)",
                        letterSpacing: "0.18em",
                      }}
                    >
                      {m.label}
                    </div>
                    <p
                      className="mt-1 font-body text-xs italic"
                      style={{ color: "var(--ink-secondary)" }}
                    >
                      {m.desc}
                    </p>
                  </motion.button>
                </RadioGroup.Item>
              );
            })}
          </RadioGroup.Root>
        </div>

        {error && (
          <div
            className="p-3 font-body text-sm italic"
            style={{
              border: "1px solid var(--blood)",
              background: "rgba(139, 0, 0, 0.1)",
              color: "var(--blood)",
            }}
          >
            ❧ {error}
          </div>
        )}

        <div className="pt-2 flex items-center justify-between gap-4">
          <button
            onClick={onBack}
            className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
            style={{ color: "var(--ink-faded)" }}
          >
            ← Back
          </button>
          <button
            onClick={onSubmit}
            disabled={isPending}
            className="font-display text-sm uppercase tracking-grimoire-wide px-8 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright disabled:opacity-50"
            style={{
              color: "var(--gold-bright)",
              border: "1px solid var(--gold-bright)",
              outline: "1px solid var(--gold-deep)",
              outlineOffset: "3px",
              background: "rgba(212, 175, 55, 0.1)",
            }}
          >
            {isPending ? "Inscribing…" : "Let the Tale Begin"}
          </button>
        </div>
      </div>
    </div>
  );
}
