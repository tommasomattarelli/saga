import * as Accordion from "@radix-ui/react-accordion";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { Drawer } from "../../../shared/ui/drawer";
import type { Quest } from "../../../shared/types";

function QuestEntry({ quest }: { quest: Quest }) {
  const isDone = quest.status === "completed" || quest.status === "failed";

  return (
    <div
      className="mb-4 p-3"
      style={{
        border: `1px solid ${isDone ? "var(--gold-deep)" : "var(--gold-bright)"}`,
        background: isDone ? "transparent" : "rgba(212, 175, 55, 0.05)",
        opacity: isDone ? 0.6 : 1,
      }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={{ color: "var(--gold-deep)", fontSize: 14 }}>✦</span>
        <h4
          className="font-display text-sm uppercase"
          style={{
            color: "var(--gold-bright)",
            letterSpacing: "0.15em",
            textDecoration: isDone ? "line-through" : "none",
          }}
        >
          {quest.name}
        </h4>
      </div>
      <p
        className="font-body italic text-sm mb-2"
        style={{ color: "var(--ink-primary)" }}
      >
        {quest.description}
      </p>
      {quest.objectives && quest.objectives.length > 0 && (
        <ul className="space-y-0.5">
          {quest.objectives.map((obj, i) => {
            /* Convention: completed objectives prefixed with [x] from backend */
            const done = obj.startsWith("[x]") || obj.startsWith("[X]");
            const text = done ? obj.replace(/^\[x\]\s*/i, "") : obj;
            return (
              <li
                key={i}
                className="flex items-start gap-2 font-body text-xs"
                style={{
                  color: done ? "var(--ink-faded)" : "var(--ink-secondary)",
                  textDecoration: done ? "line-through" : "none",
                }}
              >
                <span style={{ color: done ? "var(--gold-deep)" : "var(--ink-faded)", flexShrink: 0 }}>
                  {done ? "◆" : "◇"}
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
      title="The Ledger"
    >
      <p
        className="font-display text-[10px] uppercase mb-4"
        style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
      >
        Deeds &amp; Oaths
      </p>

      {/* Active quests */}
      {activeQuests.length === 0 ? (
        <p className="font-body italic text-sm mb-6" style={{ color: "var(--ink-faded)" }}>
          No oaths yet sworn.
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
              className="flex items-center gap-2 w-full mb-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
              style={{ color: "var(--ink-faded)" }}
            >
              <span className="font-display text-[10px] uppercase" style={{ letterSpacing: "0.25em" }}>
                Completed Deeds
              </span>
              <span className="font-body text-xs">({completedQuests.length})</span>
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
        className="mt-auto pt-4 font-display text-[9px] uppercase text-center"
        style={{ color: "var(--ink-faded)", letterSpacing: "0.2em", borderTop: "1px solid var(--gold-deep)" }}
      >
        {activeQuests.length} active · {completedQuests.length} completed
      </div>
    </Drawer>
  );
}
