import { motion, AnimatePresence } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { NpcRecord, WorldState } from "../../../shared/types";

/* ADR 0003 B2 — everyone hittable is an NPC record, so the scene shows a life bar
   for every living NPC present, always: not only "in combat", because there is no
   combat mode any more. The player's own bar lives in the hero badge. */

interface Props {
  worldState: WorldState | undefined;
}

export function npcsInScene(worldState: WorldState | undefined): NpcRecord[] {
  const npcs = worldState?.npcs;
  if (!npcs) return [];
  const here = worldState?.meta?.current_location ?? "";
  return Object.values(npcs).filter(
    (npc) => npc.lifecycle === "alive" && (!here || !npc.location || npc.location === here),
  );
}

function LifeBar({ npc }: { npc: NpcRecord }) {
  /* A record with no statblock predates ADR 0003's v8 rung. Show the name and stop —
     rendering 0/0 makes a healthy person look dead. */
  const max = npc.max_hp ?? 0;
  const current = npc.hp ?? max;
  const hasVitals = max > 0;
  const pct = hasVitals ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  const wounded = pct <= 33;

  return (
    <div
      className="flex flex-shrink-0 flex-col items-center rounded-lg px-3 py-2"
      style={{ width: 110, border: "1px solid var(--line)" }}
    >
      <span
        className="w-full truncate text-center font-display text-[13px] font-semibold"
        style={{ color: "var(--ink-primary)" }}
      >
        {npc.name}
      </span>
      {hasVitals && (
        <>
          <div
            className="relative mt-1.5 overflow-hidden rounded-full"
            style={{ width: 64, height: 4, background: "var(--line)" }}
          >
            <motion.div
              className="absolute left-0 top-0 h-full rounded-full"
              style={{ background: wounded ? "var(--blood)" : "var(--ink-faded)" }}
              initial={false}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <span className="mt-0.5 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
            {current}/{max}
          </span>
        </>
      )}
    </div>
  );
}

export default function SceneLifeBars({ worldState }: Props) {
  const { t } = useTranslation();
  const present = npcsInScene(worldState);
  if (present.length === 0) return null;

  return (
    <AnimatePresence>
      <motion.div
        className="fixed bottom-0 left-0 right-0 z-50"
        initial={{ y: "100%" }}
        animate={{ y: 0 }}
        exit={{ y: "100%" }}
        transition={{ duration: 0.25, ease: "easeOut" }}
      >
        <div
          className="mx-auto max-w-[1200px] rounded-t-xl px-6 py-3"
          style={{
            background: "var(--parchment-aged)",
            border: "1px solid var(--line-strong)",
            borderBottom: "none",
          }}
        >
          <div
            className="mb-2 text-center font-display text-xs font-semibold"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("game.in_scene")}
          </div>
          <div className="flex items-end justify-start gap-3 overflow-x-auto pb-1">
            {present.map((npc, i) => (
              <LifeBar key={`${npc.name}-${i}`} npc={npc} />
            ))}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
