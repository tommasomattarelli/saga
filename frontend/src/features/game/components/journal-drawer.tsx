import * as Accordion from "@radix-ui/react-accordion";
import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { Drawer } from "../../../shared/ui/drawer";
import type { Quest } from "../../../shared/types";

function QuestEntry({ quest }: { quest: Quest }) {
  const isDone = quest.status === "completed" || quest.status === "failed";

  return (
    <div
      className="mb-3 rounded-lg p-3"
      style={{
        border: `1px solid ${isDone ? "var(--line)" : "var(--line-strong)"}`,
        opacity: isDone ? 0.6 : 1,
      }}
    >
      <h4
        className="mb-1 font-display text-sm font-semibold"
        style={{
          color: isDone ? "var(--ink-secondary)" : "var(--ink-primary)",
          textDecoration: isDone ? "line-through" : "none",
        }}
      >
        {quest.name}
      </h4>
      <p className="mb-2 font-body text-sm italic" style={{ color: "var(--ink-secondary)" }}>
        {quest.description}
      </p>
      {quest.objectives && quest.objectives.length > 0 && (
        <ul className="space-y-1">
          {quest.objectives.map((obj, i) => {
            /* Convention: completed objectives prefixed with [x] from backend */
            const done = obj.startsWith("[x]") || obj.startsWith("[X]");
            const text = done ? obj.replace(/^\[x\]\s*/i, "") : obj;
            return (
              <li
                key={i}
                className="flex items-start gap-2 font-display text-xs"
                style={{
                  color: done ? "var(--ink-faded)" : "var(--ink-secondary)",
                  textDecoration: done ? "line-through" : "none",
                }}
              >
                <span
                  aria-hidden="true"
                  style={{ color: done ? "var(--accent)" : "var(--ink-faded)", flexShrink: 0 }}
                >
                  {done ? "●" : "○"}
                </span>
                {text}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default function JournalDrawer() {
  const { t } = useTranslation();
  const campaign = useGameStore((s) => s.campaign);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);

  const quests = campaign?.quests as Record<string, Quest[]> | undefined;
  const activeQuests: Quest[] = quests?.active ?? [];
  const completedQuests: Quest[] = quests?.completed ?? [];

  return (
    <Drawer
      open={sidePanel === "quests"}
      onClose={() => setSidePanel(null)}
      title={t("game.journal")}
    >
      {/* Active quests */}
      {activeQuests.length === 0 ? (
        <p className="mb-6 font-body text-sm italic" style={{ color: "var(--ink-faded)" }}>
          {t("journal.empty")}
        </p>
      ) : (
        <div className="mb-6">
          {activeQuests.map((q, i) => (
            <QuestEntry key={i} quest={q} />
          ))}
        </div>
      )}

      {/* Completed — Radix Accordion */}
      {completedQuests.length > 0 && (
        <Accordion.Root type="single" collapsible>
          <Accordion.Item value="completed">
            <Accordion.Trigger
              className="mb-2 flex w-full items-center gap-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              style={{ color: "var(--ink-faded)" }}
            >
              <span className="font-display text-xs font-semibold">
                {t("journal.completed")} ({completedQuests.length})
              </span>
            </Accordion.Trigger>
            <Accordion.Content>
              {completedQuests.map((q, i) => (
                <QuestEntry key={i} quest={q} />
              ))}
            </Accordion.Content>
          </Accordion.Item>
        </Accordion.Root>
      )}

      {/* Footer count */}
      <div
        className="mt-auto pt-4 text-center font-display text-[11px]"
        style={{ color: "var(--ink-faded)", borderTop: "1px solid var(--line)" }}
      >
        {t("journal.counts", { active: activeQuests.length, completed: completedQuests.length })}
      </div>
    </Drawer>
  );
}
