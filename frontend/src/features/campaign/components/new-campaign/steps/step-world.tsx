import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
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

export default function StepWorld({ templates, isLoading, selectedTemplate, onSelect }: Props) {
  const { t } = useTranslation();

  return (
    <div>
      <div className="mb-6">
        <h2 className="font-display text-lg font-semibold" style={{ color: "var(--ink-primary)" }}>
          {t("wizard.world_title")}
        </h2>
        <p className="mt-1 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
          {t("wizard.world_hint")}
        </p>
      </div>

      {isLoading && (
        <div className="py-10 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
          {t("wizard.world_loading")}
        </div>
      )}

      {!isLoading && (!templates || templates.length === 0) && (
        <div
          className="rounded-lg px-4 py-3 font-display text-sm"
          style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
        >
          {t("wizard.world_empty")}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {templates?.map((tpl) => {
          const selected = selectedTemplate?.id === tpl.id;
          return (
            <motion.button
              key={tpl.id}
              onClick={() => onSelect(tpl)}
              whileHover={{ y: -2 }}
              transition={{ type: "spring", stiffness: 300, damping: 22 }}
              className="rounded-xl p-5 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              style={{
                border: `1px solid ${selected ? "var(--accent)" : "var(--line-strong)"}`,
                background: "var(--parchment-aged)",
              }}
            >
              <h3
                className="font-display text-[15px] font-semibold"
                style={{ color: selected ? "var(--accent)" : "var(--ink-primary)" }}
              >
                {tpl.name}
              </h3>
              <p className="mt-1.5 font-body text-sm" style={{ color: "var(--ink-secondary)" }}>
                {tpl.description}
              </p>
              <div className="mt-3 font-display text-xs" style={{ color: "var(--ink-faded)" }}>
                {difficultyLabel(tpl.difficulty)} · {t("wizard.by")} {tpl.author}
              </div>
              {tpl.tags && tpl.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {tpl.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full px-2 py-0.5 font-display text-[11px]"
                      style={{ color: "var(--ink-faded)", border: "1px solid var(--line)" }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
