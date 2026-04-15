import type { CombatState } from "../../../shared/types";

interface CombatTrackerProps {
  combatState: CombatState;
}

function HpBar({ current, max }: { current: number; max: number }) {
  const pct = max > 0 ? (current / max) * 100 : 0;
  const color = pct > 50 ? "#4a7c59" : pct > 25 ? "#c4943a" : "#cc3333";
  return (
    <div
      style={{
        width: "60px",
        height: "8px",
        background: "#333",
        borderRadius: "4px",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          transition: "width 0.3s ease",
        }}
      />
    </div>
  );
}

export default function CombatTracker({ combatState }: CombatTrackerProps) {
  if (!combatState.active) return null;

  return (
    <div
      className="combat-tracker"
      style={{
        position: "fixed",
        top: "80px",
        right: "16px",
        width: "220px",
        background: "rgba(30, 10, 10, 0.95)",
        border: "1px solid #cc3333",
        borderRadius: "8px",
        padding: "12px",
        zIndex: 100,
        fontFamily: "monospace",
        fontSize: "13px",
        color: "#e0d0c0",
      }}
    >
      <div
        style={{
          fontWeight: "bold",
          marginBottom: "8px",
          color: "#cc3333",
          textAlign: "center",
        }}
      >
        COMBAT - Round {combatState.round}
      </div>

      {combatState.initiative_order.map((c, i) => {
        const isCurrent = i === combatState.current_turn_index;
        const isDead = c.hp <= 0;
        return (
          <div
            key={`${c.name}-${i}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "4px 6px",
              marginBottom: "2px",
              borderRadius: "4px",
              background: isCurrent ? "rgba(204, 51, 51, 0.2)" : "transparent",
              opacity: isDead ? 0.4 : 1,
              borderLeft: isCurrent ? "2px solid #cc3333" : "2px solid transparent",
            }}
          >
            <span style={{ width: "14px", fontSize: "10px", color: "#888" }}>{c.initiative}</span>
            <span
              style={{
                flex: 1,
                color:
                  c.type === "player" ? "#8bc4ff" : c.type === "companion" ? "#8bff8b" : "#ff8b8b",
                textDecoration: isDead ? "line-through" : "none",
              }}
            >
              {c.name}
            </span>
            <HpBar current={c.hp} max={c.max_hp} />
            <span style={{ width: "40px", textAlign: "right", fontSize: "11px" }}>
              {c.hp}/{c.max_hp}
            </span>
          </div>
        );
      })}
    </div>
  );
}
