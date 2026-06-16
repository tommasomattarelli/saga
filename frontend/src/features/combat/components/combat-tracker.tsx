import { motion, AnimatePresence } from "framer-motion";
import { OrnamentDivider } from "../../../shared/ui/ornament-divider";
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
  const pct = max > 0 ? (current / max) * 100 : 0;
  return (
    <div
      className="mt-1 relative overflow-hidden"
      style={{
        width: 64,
        height: 5,
        border: "1px solid var(--gold-deep)",
        background: "rgba(0,0,0,0.3)",
      }}
    >
      <motion.div
        className="h-full absolute left-0 top-0"
        style={{ background: isPlayer ? "var(--gold-bright)" : "var(--blood)" }}
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
  const glyph = isPlayer ? "❖" : "▲";

  return (
    <div
      className="flex-shrink-0 flex flex-col items-center px-3 py-2 transition-all"
      style={{
        width: 110,
        border: `1px solid ${isCurrent ? "var(--gold-bright)" : "var(--gold-deep)"}`,
        background: isCurrent ? "rgba(212, 175, 55, 0.15)" : "rgba(42, 26, 16, 0.6)",
        boxShadow: isCurrent ? "0 0 18px rgba(212,175,55,0.4)" : "none",
        opacity: isDead ? 0.35 : 1,
      }}
    >
      {/* Type glyph + initiative */}
      <div className="flex items-center gap-1 mb-0.5">
        <span
          className="font-display text-xs"
          style={{ color: isPlayer ? "var(--gold-bright)" : "var(--blood)" }}
        >
          {glyph}
        </span>
        <span
          className="font-display text-[10px]"
          style={{ color: "var(--ink-faded)", letterSpacing: "0.1em" }}
        >
          {combatant.initiative}
        </span>
      </div>
      {/* Name */}
      <span
        className="font-display text-[10px] uppercase text-center truncate w-full text-center"
        style={{
          color: isPlayer ? "var(--gold-bright)" : "var(--ink-primary)",
          letterSpacing: "0.12em",
          textDecoration: isDead ? "line-through" : "none",
        }}
      >
        {combatant.name}
      </span>
      {/* HP bar */}
      <CombatHpBar current={combatant.hp} max={combatant.max_hp} isPlayer={isPlayer} />
      <span
        className="mt-0.5 font-body text-[10px]"
        style={{ color: "var(--ink-faded)" }}
      >
        {combatant.hp}/{combatant.max_hp}
      </span>
      {/* Your turn label */}
      {isCurrent && (
        <span
          className="mt-0.5 font-body italic text-[9px]"
          style={{ color: "var(--gold-bright)" }}
        >
          ◀ your turn
        </span>
      )}
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
        transition={{ duration: 0.5, ease: [0.77, 0, 0.175, 1] }}
      >
        <div
          className="max-w-[1200px] mx-auto px-6 py-3"
          style={{
            background: "var(--parchment-aged)",
            border: "1px solid var(--gold-deep)",
            borderBottom: "none",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-center gap-3 mb-2">
            <span
              className="font-display text-xs uppercase"
              style={{ color: "var(--gold-bright)", letterSpacing: "0.3em" }}
            >
              COMBAT - Round {combatState.round}
            </span>
          </div>
          <OrnamentDivider variant="flourish-a" className="!my-1" />

          {/* Combatant cards — horizontal scroll; empty guard prevents crash */}
          {combatState.initiative_order.length === 0 ? (
            <div
              className="py-2 text-center font-body italic text-xs"
              style={{ color: "var(--ink-faded)" }}
            >
              Awaiting initiative…
            </div>
          ) : (
            <div className="flex items-end gap-3 overflow-x-auto pb-1 justify-start">
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
