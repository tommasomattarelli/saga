import { motion, AnimatePresence } from "framer-motion";
import type { CombatState } from "../../../shared/types";

interface CombatTrackerProps {
  combatState: CombatState;
}

function CombatHpBar({
  current,
  max,
  isPlayer,
}: {
  current: number;
  max: number;
  isPlayer: boolean;
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
  return (
    <div
      className="relative mt-1.5 overflow-hidden rounded-full"
      style={{ width: 64, height: 4, background: "var(--line)" }}
    >
      <motion.div
        className="absolute left-0 top-0 h-full rounded-full"
        style={{ background: isPlayer ? "var(--accent)" : "var(--blood)" }}
        initial={false}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5 }}
      />
    </div>
  );
}

function CombatantCard({
  combatant,
  isCurrent,
}: {
  combatant: CombatState["initiative_order"][number];
  isCurrent: boolean;
}) {
  const isPlayer = combatant.type === "player";
  const isDead = combatant.hp <= 0;

  return (
    <div
      className="flex flex-shrink-0 flex-col items-center rounded-lg px-3 py-2 transition-all"
      style={{
        width: 110,
        border: `1px solid ${isCurrent ? "var(--accent)" : "var(--line)"}`,
        opacity: isDead ? 0.35 : 1,
      }}
    >
      <span
        className="font-display text-[11px]"
        style={{ color: "var(--ink-faded)", letterSpacing: "0.06em" }}
      >
        {combatant.initiative}
      </span>
      <span
        className="w-full truncate text-center font-display text-[13px] font-semibold"
        style={{
          color: isPlayer ? "var(--accent)" : "var(--ink-primary)",
          textDecoration: isDead ? "line-through" : "none",
        }}
      >
        {combatant.name}
      </span>
      <CombatHpBar current={combatant.hp} max={combatant.max_hp} isPlayer={isPlayer} />
      <span className="mt-0.5 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
        {combatant.hp}/{combatant.max_hp}
      </span>
    </div>
  );
}

export default function CombatTracker({ combatState }: CombatTrackerProps) {
  if (!combatState.active) return null;

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
          {/* Header */}
          <div
            className="mb-2 text-center font-display text-xs font-semibold"
            style={{ color: "var(--ink-secondary)" }}
          >
            Combat · Round {combatState.round}
          </div>

          {/* Combatant cards — horizontal scroll; empty guard prevents crash */}
          {combatState.initiative_order.length === 0 ? (
            <div
              className="py-2 text-center font-display text-xs"
              style={{ color: "var(--ink-faded)" }}
            >
              Awaiting initiative…
            </div>
          ) : (
            <div className="flex items-end justify-start gap-3 overflow-x-auto pb-1">
              {combatState.initiative_order.map((c, i) => (
                <CombatantCard
                  key={`${c.name}-${i}`}
                  combatant={c}
                  isCurrent={i === combatState.current_turn_index}
                />
              ))}
            </div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
