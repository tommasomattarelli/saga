import type { TemplateOption } from "../../../../../shared/api/client";

interface Props {
  templates: TemplateOption[] | undefined;
  isLoading: boolean;
  selectedTemplate: TemplateOption | null;
  onSelect: (t: TemplateOption) => void;
}

function difficultyLabel(d: number): string {
  if (d <= 3) return "Beginner";
  if (d <= 6) return "Moderate";
  return "Hardcore";
}

export default function StepWorld({ templates, isLoading, selectedTemplate, onSelect }: Props) {
  return (
    <div>
      <h2 className="mb-1 font-display text-xl text-parchment-200">Choose your world</h2>
      <p className="mb-6 text-sm text-parchment-500">
        Each template is a different story, setting, and challenge.
      </p>

      {isLoading && (
        <div className="py-8 text-center text-parchment-400">Loading worlds...</div>
      )}

      {!isLoading && (!templates || templates.length === 0) && (
        <div className="rounded-lg border border-red-500/30 bg-red-900/20 p-4 text-sm text-red-400">
          No templates found. Make sure the backend seeded the templates on startup.
        </div>
      )}

      <div className="space-y-3">
        {templates?.map((t) => (
          <button
            key={t.id}
            onClick={() => onSelect(t)}
            className={`w-full rounded-lg border p-4 text-left transition-all ${
              selectedTemplate?.id === t.id
                ? "border-gold-500 bg-parchment-800/60"
                : "border-parchment-700/30 bg-parchment-900/60 hover:border-gold-500/40 hover:bg-parchment-800/40"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="font-display text-lg text-gold-400">{t.name}</h3>
                <p className="mt-1 text-sm text-parchment-400">{t.description}</p>
              </div>
              <span className="mt-1 shrink-0 text-xs text-parchment-500">
                {difficultyLabel(t.difficulty)} &middot; by {t.author}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {t.tags?.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-parchment-700/30 px-2 py-0.5 text-xs text-parchment-500"
                >
                  {tag}
                </span>
              ))}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
