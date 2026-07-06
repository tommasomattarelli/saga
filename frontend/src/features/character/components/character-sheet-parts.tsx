import { useState } from "react";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { CharacterData } from "../../../shared/types";
import { getHP, abilityMod } from "../../../shared/utils/dnd";

const KNOWN_ABILITIES = [
  "strength",
  "dexterity",
  "constitution",
  "intelligence",
  "wisdom",
  "charisma",
];

// Canonical order for the six core abilities, with any extra (e.g. "luck") appended.
function orderedAbilities(abilities: Record<string, number>): string[] {
  const known = KNOWN_ABILITIES.filter((a) => a in abilities);
  const extra = Object.keys(abilities).filter((a) => !KNOWN_ABILITIES.includes(a));
  return [...known, ...extra];
}

type TabKey = "stats" | "inventory" | "skills" | "reputation" | "background";
const TABS: TabKey[] = ["stats", "inventory", "skills", "reputation", "background"];

/* One row per entry — the shared list pattern of the sheet (no bars: abilities are uncapped) */
function Row({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  return (
    <div
      className="flex items-baseline justify-between border-b py-2 last:border-b-0"
      style={{ borderColor: "var(--line)" }}
    >
      <span className="font-display text-sm" style={{ color: "var(--ink-secondary)" }}>
        {left}
      </span>
      <span className="font-display text-sm">{right}</span>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <p className="py-2 font-body text-sm italic" style={{ color: "var(--ink-faded)" }}>
      {text}
    </p>
  );
}

function TabContent({ tab, char }: { tab: TabKey; char: CharacterData }) {
  const { t } = useTranslation();

  if (tab === "stats") {
    return (
      <div>
        {orderedAbilities(char.abilities ?? {}).map((ab) => {
          const score = char.abilities?.[ab] ?? 10;
          return (
            <Row
              key={ab}
              left={<span className="capitalize">{ab}</span>}
              right={
                <>
                  <span className="font-semibold" style={{ color: "var(--ink-primary)" }}>
                    {score}
                  </span>{" "}
                  <span className="text-xs" style={{ color: "var(--accent)" }}>
                    {abilityMod(score)}
                  </span>
                </>
              }
            />
          );
        })}
      </div>
    );
  }

  if (tab === "inventory") {
    const items = char.inventory ?? [];
    if (items.length === 0) return <EmptyLine text={t("char.empty_inventory")} />;
    return (
      <div>
        {items.map((item, i) => (
          <Row
            key={i}
            left={<span style={{ color: "var(--ink-primary)" }}>{item.name}</span>}
            right={
              item.quantity > 1 ? (
                <span style={{ color: "var(--ink-faded)" }}>×{item.quantity}</span>
              ) : null
            }
          />
        ))}
      </div>
    );
  }

  if (tab === "skills") {
    const skills = Object.entries(char.skills ?? {});
    if (skills.length === 0) return <EmptyLine text={t("char.empty_skills")} />;
    return (
      <div>
        {skills.map(([skill, data]) => (
          <Row
            key={skill}
            left={<span className="capitalize">{skill}</span>}
            right={<span style={{ color: "var(--ink-faded)" }}>Lv {data.level}</span>}
          />
        ))}
      </div>
    );
  }

  if (tab === "reputation") {
    const reps = Object.entries(char.reputation ?? {});
    if (reps.length === 0) return <EmptyLine text={t("char.empty_reputation")} />;
    return (
      <div>
        {reps.map(([faction, score]) => (
          <Row
            key={faction}
            left={faction}
            right={
              <span style={{ color: score >= 0 ? "var(--accent)" : "var(--blood)" }}>
                {score >= 0 ? "+" : ""}
                {score}
              </span>
            }
          />
        ))}
      </div>
    );
  }

  // background
  if (!char.background) return <EmptyLine text={t("char.empty_background")} />;
  return (
    <p
      className="font-body text-base italic"
      style={{ color: "var(--ink-primary)", lineHeight: 1.62 }}
    >
      {char.background}
    </p>
  );
}

export function CharacterSheetBody({ char }: { char: CharacterData | null }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<TabKey>("stats");

  if (!char || !char.name) {
    return (
      <p className="p-8 font-body italic" style={{ color: "var(--ink-faded)" }}>
        {t("char.no_data")}
      </p>
    );
  }
  const hp = getHP(char);
  const hpPct = hp.max > 0 ? Math.max(0, Math.min(100, (hp.current / hp.max) * 100)) : 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Header — identity + vitals */}
      <div
        className="flex items-center gap-4 px-6 py-5"
        style={{ borderBottom: "1px solid var(--line)" }}
      >
        <div
          aria-hidden="true"
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full font-display text-lg font-semibold"
          style={{
            border: "1px solid var(--line-strong)",
            color: "var(--accent)",
            background: "var(--parchment-aged)",
          }}
        >
          {char.name[0]?.toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h2
              className="font-display text-lg font-semibold truncate"
              style={{ color: "var(--ink-primary)" }}
            >
              {char.name}
            </h2>
            <span className="font-display text-sm" style={{ color: "var(--ink-faded)" }}>
              {char.archetype ?? ""} · Lv {char.level}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <div
              aria-label={`HP ${hp.current} of ${hp.max}`}
              className="h-1.5 w-36 overflow-hidden rounded-full"
              style={{ background: "var(--line)" }}
            >
              <motion.div
                className="h-full rounded-full"
                style={{ background: "var(--blood)" }}
                initial={false}
                animate={{ width: `${hpPct}%` }}
                transition={{ duration: 0.6, ease: "easeOut" }}
              />
            </div>
            <span className="font-display text-xs" style={{ color: "var(--ink-secondary)" }}>
              HP {hp.current}/{hp.max}
            </span>
            <span className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
              AC {char.ac} · XP {char.xp} · Gold {char.gold}
            </span>
          </div>
        </div>
      </div>

      {/* Rail + content */}
      <div className="flex min-h-0 flex-1">
        <nav
          className="flex w-[150px] shrink-0 flex-col py-3"
          style={{ borderRight: "1px solid var(--line)" }}
          aria-label="Character sections"
        >
          {TABS.map((key) => {
            const active = tab === key;
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                aria-current={active ? "true" : undefined}
                className="px-5 py-2 text-left font-display text-[13px] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                style={{
                  color: active ? "var(--accent)" : "var(--ink-faded)",
                  borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`,
                  background: active ? "rgba(143, 184, 172, 0.05)" : "transparent",
                }}
              >
                {t(`char.${key}`)}
              </button>
            );
          })}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <TabContent tab={tab} char={char} />
        </div>
      </div>
    </div>
  );
}
