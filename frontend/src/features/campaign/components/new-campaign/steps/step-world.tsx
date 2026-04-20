import { motion } from "framer-motion";
import {
  Castle,
  ElvenCastle,
  TowerFall,
  Mountains,
  DragonHead,
  Compass,
} from "react-game-icons";
import type { TemplateOption } from "../../../../../shared/api/client";

interface Props {
  templates: TemplateOption[] | undefined;
  isLoading: boolean;
  selectedTemplate: TemplateOption | null;
  onSelect: (t: TemplateOption) => void;
}

function difficultyLabel(d: number): string {
  if (d <= 3) return "Gentle";
  if (d <= 6) return "Perilous";
  return "Unforgiving";
}

/* Pick a deterministic kingdom icon from template id — so each world gets its sigil */
const KINGDOM_ICONS = [Castle, ElvenCastle, TowerFall, Mountains, DragonHead, Compass];
function kingdomIcon(id: string) {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return KINGDOM_ICONS[hash % KINGDOM_ICONS.length];
}

export default function StepWorld({ templates, isLoading, selectedTemplate, onSelect }: Props) {
  return (
    <div>
      <div className="mb-6 text-center">
        <h2
          className="font-display text-2xl uppercase"
          style={{ color: "var(--gold-bright)", letterSpacing: "0.22em" }}
        >
          The World Awaits
        </h2>
        <p
          className="mt-2 font-body italic text-sm"
          style={{ color: "var(--ink-secondary)" }}
        >
          Choose the realm in which thy tale shall be inscribed.
        </p>
      </div>

      {isLoading && (
        <div
          className="py-10 text-center font-body italic"
          style={{ color: "var(--ink-faded)" }}
        >
          Unfurling the atlas…
        </div>
      )}

      {!isLoading && (!templates || templates.length === 0) && (
        <div
          className="p-4 font-body text-sm text-center"
          style={{
            border: "1px solid var(--blood)",
            background: "rgba(139, 0, 0, 0.08)",
            color: "var(--blood)",
          }}
        >
          No realms have been charted. Ensure the keeper of tales has seeded the templates.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {templates?.map((t) => {
          const Icon = kingdomIcon(t.id);
          const selected = selectedTemplate?.id === t.id;
          return (
            <motion.button
              key={t.id}
              onClick={() => onSelect(t)}
              whileHover={{ y: -3 }}
              transition={{ type: "spring", stiffness: 300, damping: 22 }}
              className="relative p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
              style={{
                background: selected
                  ? "rgba(212, 175, 55, 0.12)"
                  : "rgba(244, 232, 208, 0.04)",
                border: `1px solid ${selected ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                boxShadow: selected ? "0 0 24px rgba(212,175,55,0.25)" : "none",
              }}
            >
              <div className="flex items-start gap-4">
                <div
                  className="shrink-0 flex items-center justify-center"
                  style={{
                    width: 56,
                    height: 56,
                    color: "var(--gold-bright)",
                    fontSize: 40,
                  }}
                >
                  <Icon />
                </div>
                <div className="flex-1 min-w-0">
                  <h3
                    className="font-display text-lg uppercase"
                    style={{ color: "var(--gold-bright)", letterSpacing: "0.15em" }}
                  >
                    {t.name}
                  </h3>
                  <p
                    className="mt-1 font-body text-sm"
                    style={{ color: "var(--ink-secondary)" }}
                  >
                    {t.description}
                  </p>
                  <div
                    className="mt-3 flex items-center gap-2 flex-wrap font-display text-[10px] uppercase"
                    style={{
                      color: "var(--ink-faded)",
                      letterSpacing: "0.2em",
                    }}
                  >
                    <span>{difficultyLabel(t.difficulty)}</span>
                    <span aria-hidden="true">·</span>
                    <span>Scribed by {t.author}</span>
                  </div>
                  {t.tags && t.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {t.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 font-body text-xs italic"
                          style={{
                            color: "var(--ink-faded)",
                            border: "1px solid var(--gold-deep)",
                            opacity: 0.8,
                          }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
