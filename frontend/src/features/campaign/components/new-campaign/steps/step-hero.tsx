import { motion } from "framer-motion";
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
  const preset = CLASS_PRESETS[form.archetype];

  return (
    <div>
      <div className="mb-6 text-center">
        <h2
          className="font-display text-2xl uppercase"
          style={{ color: "var(--gold-bright)", letterSpacing: "0.22em" }}
        >
          The Hero
        </h2>
        <p
          className="mt-2 font-body italic text-sm"
          style={{ color: "var(--ink-secondary)" }}
        >
          Walking the paths of{" "}
          <span style={{ color: "var(--gold-bright)" }}>{selectedTemplate.name}</span>
          . Who dost thou become?
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_260px] gap-8">
        {/* Class grid */}
        <div>
          <label
            className="block mb-3 font-display text-[10px] uppercase"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
          >
            Choose thy calling
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
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
                  className="relative p-3 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
                  style={{
                    border: `1px solid ${selected ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                    background: selected
                      ? "rgba(212, 175, 55, 0.12)"
                      : "rgba(244, 232, 208, 0.04)",
                    boxShadow: selected ? "0 0 16px rgba(212,175,55,0.3)" : "none",
                  }}
                >
                  <div
                    className="mx-auto mb-1.5 flex items-center justify-center"
                    style={{
                      width: 48,
                      height: 48,
                      color: selected ? "var(--gold-bright)" : "var(--gold-deep)",
                      fontSize: 36,
                    }}
                  >
                    <Icon />
                  </div>
                  <div
                    className="font-display text-xs uppercase"
                    style={{
                      color: selected ? "var(--gold-bright)" : "var(--ink-secondary)",
                      letterSpacing: "0.15em",
                    }}
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
              className="block mb-2 font-display text-[10px] uppercase"
              style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
            >
              Thy name
            </label>
            <input
              id="hero-name"
              type="text"
              value={form.heroName}
              onChange={(e) => onChange({ heroName: e.target.value })}
              placeholder="Leave blank to walk as a stranger…"
              className="w-full bg-transparent py-2 font-body text-lg italic focus:outline-none"
              style={{
                color: "var(--ink-primary)",
                borderBottom: "1px solid var(--gold-deep)",
              }}
            />
          </div>
        </div>

        {/* Preview sigil */}
        <aside
          className="p-4 self-start"
          style={{
            border: "1px solid var(--gold-deep)",
            background: "rgba(244, 232, 208, 0.03)",
          }}
        >
          <div
            className="font-display text-[9px] uppercase text-center mb-3"
            style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
          >
            Sigil of the Hero
          </div>
          <div className="text-center mb-3">
            <div
              className="font-display text-lg uppercase"
              style={{ color: "var(--gold-bright)", letterSpacing: "0.12em" }}
            >
              {form.heroName || "The Stranger"}
            </div>
            <div
              className="font-body text-sm italic"
              style={{ color: "var(--ink-secondary)" }}
            >
              {preset.label}
            </div>
          </div>

          <div className="flex items-center justify-between mb-3 font-body text-xs" style={{ color: "var(--ink-secondary)" }}>
            <span>HP</span>
            <span style={{ color: "var(--gold-bright)" }}>
              {preset.baseHp} / {preset.baseHp}
            </span>
          </div>
          <div
            className="h-1.5 mb-4 overflow-hidden"
            style={{ background: "var(--gold-deep)", opacity: 0.3 }}
          >
            <div className="h-full" style={{ background: "var(--gold-bright)", width: "100%" }} />
          </div>

          <div className="grid grid-cols-3 gap-2">
            {Object.entries(preset.abilities).map(([ability, score]) => (
              <div
                key={ability}
                className="text-center py-1.5"
                style={{ border: "1px solid var(--gold-deep)" }}
              >
                <div
                  className="font-display text-[9px] uppercase"
                  style={{ color: "var(--ink-faded)", letterSpacing: "0.2em" }}
                >
                  {ability.slice(0, 3)}
                </div>
                <div
                  className="font-display text-base"
                  style={{ color: "var(--gold-bright)" }}
                >
                  {score}
                </div>
                <div className="font-body text-[10px]" style={{ color: "var(--ink-secondary)" }}>
                  {abilityMod(score)}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="mt-8 flex items-center justify-between gap-4">
        <button
          onClick={onBack}
          className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
          style={{ color: "var(--ink-faded)" }}
        >
          ← Back
        </button>
        <button
          onClick={onNext}
          className="font-display text-sm uppercase tracking-grimoire-wide px-6 py-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
          style={{
            color: "var(--gold-bright)",
            border: "1px solid var(--gold-bright)",
            outline: "1px solid var(--gold-deep)",
            outlineOffset: "3px",
            background: "rgba(212, 175, 55, 0.08)",
          }}
        >
          Name thy Fate →
        </button>
      </div>
    </div>
  );
}
