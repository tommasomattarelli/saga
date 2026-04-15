import { DEATH_MODES } from "../../../data/class-presets";
import type { TemplateOption } from "../../../../../shared/api/client";

interface HeroForm {
  heroName: string;
  campaignName: string;
  deathMode: string;
}

interface Props {
  form: HeroForm;
  selectedTemplate: TemplateOption;
  onChange: (patch: Partial<HeroForm>) => void;
  onBack: () => void;
  onNext: () => void;
}

export default function StepHero({ form, selectedTemplate, onChange, onBack, onNext }: Props) {
  return (
    <div>
      <h2 className="mb-1 font-display text-xl text-parchment-200">Name your hero</h2>
      <p className="mb-6 text-sm text-parchment-500">
        Playing <span className="text-gold-400">{selectedTemplate.name}</span>
      </p>

      <div className="space-y-5">
        <div>
          <label htmlFor="hero-name" className="mb-1.5 block text-sm text-parchment-300">
            Hero Name
          </label>
          <input
            id="hero-name"
            type="text"
            value={form.heroName}
            onChange={(e) => onChange({ heroName: e.target.value })}
            placeholder="Leave blank for a mysterious stranger..."
            className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
          />
        </div>

        <div>
          <label htmlFor="campaign-name" className="mb-1.5 block text-sm text-parchment-300">
            Campaign Name <span className="text-parchment-600">(optional)</span>
          </label>
          <input
            id="campaign-name"
            type="text"
            value={form.campaignName}
            onChange={(e) => onChange({ campaignName: e.target.value })}
            placeholder={`${form.heroName || "The Stranger"}'s Adventure`}
            className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm text-parchment-300">Death Mode</label>
          <div className="space-y-2">
            {DEATH_MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => onChange({ deathMode: m.value })}
                className={`w-full rounded-lg border px-4 py-3 text-left transition-all ${
                  form.deathMode === m.value
                    ? "border-gold-500 bg-parchment-800/60"
                    : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/30"
                }`}
              >
                <span className="text-sm font-medium text-parchment-200">{m.label}</span>
                <p className="mt-0.5 text-xs text-parchment-500">{m.desc}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={onBack}
            className="rounded-lg border border-parchment-700/30 px-4 py-2.5 text-sm text-parchment-400 hover:bg-parchment-800/40"
          >
            Back
          </button>
          <button
            onClick={onNext}
            className="flex-1 rounded-lg border border-gold-500/30 bg-gold-900/20 py-2.5 text-sm font-medium text-gold-400 transition hover:bg-gold-900/40"
          >
            Next: Create Character &rarr;
          </button>
        </div>
      </div>
    </div>
  );
}
