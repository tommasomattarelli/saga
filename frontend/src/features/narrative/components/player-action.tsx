import { useGameStore } from "../../../shared/stores/game-store";

/* Player action echo — italic line with an accent hairline, quiet against the narration */
export default function PlayerAction({ action }: { action: string }) {
  const heroName = useGameStore((s) => s.campaign?.character_data?.name ?? "Hero");

  return (
    <div className="my-6 pl-4" style={{ borderLeft: "2px solid var(--accent)" }}>
      <div className="font-display text-xs font-semibold mb-1" style={{ color: "var(--accent)" }}>
        {heroName}
      </div>
      <p className="font-body italic text-base" style={{ color: "var(--ink-secondary)" }}>
        {action}
      </p>
    </div>
  );
}
