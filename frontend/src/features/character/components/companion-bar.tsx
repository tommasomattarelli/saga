import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";

export default function CompanionBar() {
  const campaign = useGameStore((s) => s.campaign);
  const showCompanionBar = useUIStore((s) => s.showCompanionBar);

  if (!showCompanionBar || !campaign?.world_state?.companions) return null;

  const companions = campaign.world_state.companions;

  return (
    <div
      className="flex gap-3 px-6 py-2"
      style={{ background: "var(--parchment-aged)", borderBottom: "1px solid var(--line)" }}
    >
      {Object.entries(companions).map(([key, c]) => {
        const hpPercent = Math.max(0, Math.min(100, (c.hp / c.max_hp) * 100));

        return (
          <div key={key} className="flex items-center gap-2.5">
            <span
              className="font-display text-[13px] font-semibold"
              style={{ color: "var(--ink-primary)" }}
            >
              {c.name}
            </span>
            <span className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
              {c.mood}
            </span>
            <div
              aria-label={`${c.name} HP ${c.hp} of ${c.max_hp}`}
              className="h-1 w-14 overflow-hidden rounded-full"
              style={{ background: "var(--line)" }}
            >
              <div
                className="h-full rounded-full"
                style={{ width: `${hpPercent}%`, background: "var(--blood)" }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
