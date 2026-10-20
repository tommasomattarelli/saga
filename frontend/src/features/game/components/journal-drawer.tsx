import * as Accordion from "@radix-ui/react-accordion";
import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { Drawer } from "../../../shared/ui/drawer";
import type { Quest, QuestStatus } from "../../../shared/types";

function QuestEntry({ quest, status }: { quest: Quest; status: QuestStatus }) {
  const { t } = useTranslation();
  const isConcluded = status !== "active";

  return (
    <div
      className="mb-3 rounded-lg p-3"
      style={{
        border: `1px solid ${isConcluded ? "var(--line)" : "var(--line-strong)"}`,
        opacity: isConcluded ? 0.6 : 1,
      }}
    >
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h4
          className="font-display text-sm font-semibold"
          style={{
            color: isConcluded ? "var(--ink-secondary)" : "var(--ink-primary)",
            textDecoration: isConcluded ? "line-through" : "none",
          }}
        >
          {quest.name}
        </h4>
        {status !== "active" && status !== "completed" && (
          <span
            className="font-display text-[10px] uppercase"
            style={{ color: "var(--ink-faded)" }}
          >
            {t(`journal.${status}`)}
          </span>
        )}
      </div>
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

  const quests = campaign?.quests;
  const activeQuests: Quest[] = quests?.active ?? [];
  const concludedQuests: { quest: Quest; status: QuestStatus }[] = [
    ...(quests?.completed ?? []).map((quest) => ({ quest, status: "completed" as const })),
    ...(quests?.failed ?? []).map((quest) => ({ quest, status: "failed" as const })),
    ...(quests?.abandoned ?? []).map((quest) => ({ quest, status: "abandoned" as const })),
  ];

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
          {activeQuests.map((q) => (
            <QuestEntry key={q.id} quest={q} status="active" />
          ))}
        </div>
      )}

      {/* Concluded — Radix Accordion */}
      {concludedQuests.length > 0 && (
        <Accordion.Root type="single" collapsible>
          <Accordion.Item value="concluded">
            <Accordion.Trigger
              className="mb-2 flex w-full items-center gap-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              style={{ color: "var(--ink-faded)" }}
            >
              <span className="font-display text-xs font-semibold">
                {t("journal.concluded")} ({concludedQuests.length})
              </span>
            </Accordion.Trigger>
            <Accordion.Content>
              {concludedQuests.map(({ quest, status }) => (
                <QuestEntry key={quest.id} quest={quest} status={status} />
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
        {t("journal.counts", {
          active: activeQuests.length,
          concluded: concludedQuests.length,
        })}
      </div>
    </Drawer>
  );
}
