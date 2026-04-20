import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";

export default function CompanionBar() {
  const campaign = useGameStore((s) => s.campaign);
  const showCompanionBar = useUIStore((s) => s.showCompanionBar);

  if (!showCompanionBar || !campaign?.world_state?.companions) return null;

  const companions = campaign.world_state.companions;

  return (
    <div className="flex gap-2 border-b border-parchment-700/20 bg-parchment-900/80 px-4 py-2">
      {Object.entries(companions).map(([key, companion]) => {
        const c = companion as {
          name: string;
          hp: number;
          max_hp: number;
          mood: string;
          loyalty: number;
        };
        const hpPercent = (c.hp / c.max_hp) * 100;

        return (
          <div
            key={key}
            className="flex items-center gap-2 rounded-lg border border-parchment-700/20 bg-parchment-800/30 px-3 py-1"
          >
            <div>
              <span className="text-sm font-semibold text-parchment-200">{c.name}</span>
              <span className="ml-2 text-xs text-parchment-500">{c.mood}</span>
            </div>
            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-parchment-800">
              <div className="h-full rounded-full bg-red-600" style={{ width: `${hpPercent}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
