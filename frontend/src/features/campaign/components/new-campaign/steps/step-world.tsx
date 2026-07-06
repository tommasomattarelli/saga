import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { WorldOption } from "../../../../../shared/api/client";

interface Props {
  worlds: WorldOption[] | undefined;
  isLoading: boolean;
  selectedWorld: WorldOption | null;
  onSelect: (w: WorldOption) => void;
}

export default function StepWorld({ worlds, isLoading, selectedWorld, onSelect }: Props) {
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

      {!isLoading && (!worlds || worlds.length === 0) && (
        <div
          className="rounded-lg px-4 py-3 font-display text-sm"
          style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
        >
          {t("wizard.world_empty")}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {worlds?.map((world) => {
          const selected = selectedWorld?.slug === world.slug;
          return (
            <motion.button
              key={world.slug}
              onClick={() => onSelect(world)}
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
                {world.name}
              </h3>
              <p className="mt-1.5 font-body text-sm" style={{ color: "var(--ink-secondary)" }}>
                {world.description}
              </p>
              <div className="mt-3 font-display text-xs" style={{ color: "var(--ink-faded)" }}>
                {t("wizard.by")} {world.author}
              </div>
              {world.tags && world.tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {world.tags.map((tag) => (
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
