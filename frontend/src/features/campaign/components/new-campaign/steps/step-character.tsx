import { CLASS_PRESETS } from "../../../data/class-presets";
import { abilityMod } from "../../../../../shared/utils/dnd";

interface CharacterForm {
  heroName: string;
  archetype: string;
  background: string;
}

interface Props {
  form: CharacterForm;
  onChange: (patch: Partial<CharacterForm>) => void;
  onBack: () => void;
  onSubmit: () => void;
  isPending: boolean;
  error: string | null;
}

export default function StepCharacter({ form, onChange, onBack, onSubmit, isPending, error }: Props) {
  const selectedPreset = CLASS_PRESETS[form.archetype];

  return (
    <div>
      <h2 className="mb-1 font-display text-xl text-parchment-200">Create your character</h2>
      <p className="mb-6 text-sm text-parchment-500">
        Choose a class and see your stats. You can always change later in-game.
      </p>

      <div className="space-y-5">
        <div>
          <label className="mb-2 block text-sm text-parchment-300">Class</label>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(CLASS_PRESETS).map(([key, preset]) => (
              <button
                key={key}
                type="button"
                onClick={() => onChange({ archetype: key })}
                className={`rounded-lg border px-3 py-2.5 text-left transition-all ${
                  form.archetype === key
                    ? "border-gold-500 bg-parchment-800/60"
                    : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/30"
                }`}
              >
                <span className="text-sm font-medium text-parchment-200">{preset.label}</span>
                <p className="mt-0.5 text-xs text-parchment-500">{preset.desc}</p>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label htmlFor="background" className="mb-1.5 block text-sm text-parchment-300">
            Background <span className="text-parchment-600">(optional)</span>
          </label>
          <input
            id="background"
            type="text"
            value={form.background}
            onChange={(e) => onChange({ background: e.target.value })}
            placeholder="A wandering sellsword seeking redemption..."
            className="w-full rounded-lg border border-parchment-700/30 bg-parchment-900 px-4 py-2.5 text-parchment-200 placeholder-parchment-600 focus:border-gold-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold-500/40"
          />
        </div>

        <div className="rounded-lg border border-parchment-700/30 bg-parchment-900/60 p-4">
          <h4 className="mb-3 text-sm font-semibold uppercase tracking-wider text-parchment-500">
            Character Preview
          </h4>
          <div className="mb-3 flex items-center justify-between">
            <span className="font-display text-lg text-gold-400">
              {form.heroName || "The Stranger"}
            </span>
            <span className="text-sm text-parchment-400">
              HP {selectedPreset.baseHp}/{selectedPreset.baseHp}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(selectedPreset.abilities).map(([ability, score]) => (
              <div
                key={ability}
                className="rounded border border-parchment-700/20 px-2 py-1.5 text-center"
              >
                <div className="text-xs uppercase text-parchment-500">{ability.slice(0, 3)}</div>
                <div className="font-bold text-parchment-200">{score}</div>
                <div className="text-xs text-parchment-500">{abilityMod(score)}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-4 text-sm text-parchment-400">
            <span>AC: 10</span>
            <span>Gold: 10</span>
            <span>Level: 1</span>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            onClick={onBack}
            className="rounded-lg border border-parchment-700/30 px-4 py-2.5 text-sm text-parchment-400 hover:bg-parchment-800/40"
          >
            Back
          </button>
          <button
            onClick={onSubmit}
            disabled={isPending}
            className="flex-1 rounded-lg border border-gold-500/30 bg-gold-900/20 py-2.5 text-sm font-medium text-gold-400 transition hover:bg-gold-900/40 disabled:opacity-50"
          >
            {isPending ? "Creating..." : "Begin the Saga"}
          </button>
        </div>
      </div>
    </div>
  );
}
