import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import {
  CrossedSwords,
  BatteredAxe,
  WizardStaff,
  Bowman,
  HolySymbol,
  HolyOak,
  CrystalBall,
} from "react-game-icons";
import type { ComponentType } from "react";
import { CLASS_PRESETS } from "../../../data/class-presets";
import { abilityMod } from "../../../../../shared/utils/dnd";
import type { TemplateOption } from "../../../../../shared/api/client";

interface HeroForm {
  heroName: string;
  archetype: string;
}

interface Props {
  form: HeroForm;
  selectedTemplate: TemplateOption;
  onChange: (patch: Partial<HeroForm>) => void;
  onBack: () => void;
  onNext: () => void;
}

const CLASS_ICONS: Record<string, ComponentType> = {
  warrior: CrossedSwords,
  rogue: BatteredAxe,
  mage: WizardStaff,
  ranger: Bowman,
  cleric: HolySymbol,
  bard: HolyOak,
};

const FALLBACK_ICON: ComponentType = CrystalBall;

export default function StepHero({ form, selectedTemplate, onChange, onBack, onNext }: Props) {
  const { t } = useTranslation();
  const preset = CLASS_PRESETS[form.archetype];

  return (
    <div>
      <div className="mb-6">
        <h2 className="font-display text-lg font-semibold" style={{ color: "var(--ink-primary)" }}>
          {t("wizard.hero_title")}
        </h2>
        <p className="mt-1 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
          {t("wizard.hero_hint", { world: selectedTemplate.name })}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-[1fr_260px]">
        {/* Class grid */}
        <div>
          <label
            className="mb-3 block font-display text-xs"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("wizard.class_label")}
          </label>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Object.entries(CLASS_PRESETS).map(([key, p]) => {
              const Icon = CLASS_ICONS[key] ?? FALLBACK_ICON;
              const selected = form.archetype === key;
              return (
                <motion.button
                  key={key}
                  type="button"
                  onClick={() => onChange({ archetype: key })}
                  whileHover={{ y: -2 }}
                  transition={{ type: "spring", stiffness: 300, damping: 22 }}
                  className="rounded-xl p-3 text-center focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                  style={{
                    border: `1px solid ${selected ? "var(--accent)" : "var(--line-strong)"}`,
                    background: "var(--parchment-aged)",
                  }}
                >
                  <div
                    className="mx-auto mb-1.5 flex items-center justify-center"
                    style={{
                      width: 44,
                      height: 44,
                      color: selected ? "var(--accent)" : "var(--ink-faded)",
                      fontSize: 32,
                    }}
                  >
                    <Icon />
                  </div>
                  <div
                    className="font-display text-[13px] font-semibold"
                    style={{ color: selected ? "var(--accent)" : "var(--ink-secondary)" }}
                  >
                    {p.label}
                  </div>
                </motion.button>
              );
            })}
          </div>

          {/* Hero name */}
          <div className="mt-6">
            <label
              htmlFor="hero-name"
              className="mb-1.5 block font-display text-xs"
              style={{ color: "var(--ink-secondary)" }}
            >
              {t("wizard.name_label")}
            </label>
            <input
              id="hero-name"
              type="text"
              value={form.heroName}
              onChange={(e) => onChange({ heroName: e.target.value })}
              placeholder={t("wizard.name_placeholder")}
              className="w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              style={{
                color: "var(--ink-primary)",
                background: "var(--parchment-aged)",
                border: "1px solid var(--line-strong)",
              }}
            />
          </div>
        </div>

        {/* Preview */}
        <aside
          className="self-start rounded-xl p-4"
          style={{ border: "1px solid var(--line)", background: "var(--parchment-aged)" }}
        >
          <div className="mb-3 font-display text-xs" style={{ color: "var(--ink-faded)" }}>
            {t("wizard.preview_label")}
          </div>
          <div
            className="font-display text-[15px] font-semibold"
            style={{ color: "var(--ink-primary)" }}
          >
            {form.heroName || "The Stranger"}
          </div>
          <div className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
            {preset.label} · HP {preset.baseHp}
          </div>
          <p
            className="mt-2 mb-3 font-body text-sm italic"
            style={{ color: "var(--ink-secondary)" }}
          >
            {preset.desc}
          </p>

          <div>
            {Object.entries(preset.abilities).map(([ability, score]) => (
              <div
                key={ability}
                className="flex items-baseline justify-between border-b py-1.5 last:border-b-0"
                style={{ borderColor: "var(--line)" }}
              >
                <span
                  className="font-display text-[11px] uppercase"
                  style={{ color: "var(--ink-faded)", letterSpacing: "0.08em" }}
                >
                  {ability}
                </span>
                <span className="font-display text-sm">
                  <span className="font-semibold" style={{ color: "var(--ink-primary)" }}>
                    {score}
                  </span>{" "}
                  <span className="text-xs" style={{ color: "var(--accent)" }}>
                    {abilityMod(score)}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="mt-8 flex items-center justify-between gap-4">
        <button
          onClick={onBack}
          className="px-2 py-2 font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--ink-faded)" }}
        >
          ← {t("wizard.back")}
        </button>
        <button
          onClick={onNext}
          className="rounded-lg px-6 py-2.5 font-display text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--accent)", border: "1px solid var(--accent)" }}
        >
          {t("wizard.next")} →
        </button>
      </div>
    </div>
  );
}
