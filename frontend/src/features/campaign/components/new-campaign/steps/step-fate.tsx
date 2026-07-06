import { motion } from "framer-motion";
import * as RadioGroup from "@radix-ui/react-radio-group";
import { useTranslation } from "react-i18next";
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

export default function StepFate({ form, onChange, onBack, onSubmit, isPending, error }: Props) {
  const { t } = useTranslation();

  return (
    <div>
      <div className="mb-6">
        <h2 className="font-display text-lg font-semibold" style={{ color: "var(--ink-primary)" }}>
          {t("wizard.fate_title")}
        </h2>
        <p className="mt-1 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
          {t("wizard.fate_hint")}
        </p>
      </div>

      <div className="space-y-6">
        {/* Campaign name */}
        <div>
          <label
            htmlFor="campaign-name"
            className="mb-1.5 block font-display text-xs"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("wizard.campaign_title_label")}
          </label>
          <input
            id="campaign-name"
            type="text"
            value={form.campaignName}
            onChange={(e) => onChange({ campaignName: e.target.value })}
            placeholder={`${form.heroName || "The Stranger"}'s Adventure`}
            className="w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent"
            style={{
              color: "var(--ink-primary)",
              background: "var(--parchment-aged)",
              border: "1px solid var(--line-strong)",
            }}
          />
        </div>

        {/* Background */}
        <div>
          <label
            htmlFor="background"
            className="mb-1.5 block font-display text-xs"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("wizard.origin_label")}
          </label>
          <input
            id="background"
            type="text"
            value={form.background}
            onChange={(e) => onChange({ background: e.target.value })}
            placeholder={t("wizard.origin_placeholder")}
            className="w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent"
            style={{
              color: "var(--ink-primary)",
              background: "var(--parchment-aged)",
              border: "1px solid var(--line-strong)",
            }}
          />
        </div>

        {/* Death mode */}
        <div>
          <label
            className="mb-3 block font-display text-xs"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("wizard.death_label")}
          </label>
          <RadioGroup.Root
            value={form.deathMode}
            onValueChange={(v) => onChange({ deathMode: v })}
            className="grid grid-cols-1 gap-3 sm:grid-cols-3"
          >
            {DEATH_MODES.map((m) => {
              const selected = form.deathMode === m.value;
              return (
                <RadioGroup.Item key={m.value} value={m.value} asChild>
                  <motion.button
                    whileHover={{ y: -2 }}
                    transition={{ type: "spring", stiffness: 300, damping: 22 }}
                    className="rounded-xl p-4 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                    style={{
                      border: `1px solid ${selected ? "var(--accent)" : "var(--line-strong)"}`,
                      background: "var(--parchment-aged)",
                    }}
                  >
                    <div
                      className="font-display text-sm font-semibold"
                      style={{ color: selected ? "var(--accent)" : "var(--ink-primary)" }}
                    >
                      {m.label}
                    </div>
                    <p className="mt-1 font-body text-xs" style={{ color: "var(--ink-secondary)" }}>
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
            role="alert"
            className="rounded-lg px-4 py-3 font-display text-sm"
            style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
          >
            {error}
          </div>
        )}

        <div className="flex items-center justify-between gap-4 pt-2">
          <button
            onClick={onBack}
            className="px-2 py-2 font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--ink-faded)" }}
          >
            ← {t("wizard.back")}
          </button>
          <button
            onClick={onSubmit}
            disabled={isPending}
            className="rounded-lg px-7 py-2.5 font-display text-sm font-semibold disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--accent)", border: "1px solid var(--accent)" }}
          >
            {isPending ? t("wizard.creating") : t("wizard.create")}
          </button>
        </div>
      </div>
    </div>
  );
}
