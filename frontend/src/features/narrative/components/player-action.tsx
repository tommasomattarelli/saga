import { useGameStore } from "../../../shared/stores/game-store";
import { OrnateFrame } from "../../../shared/ui/ornate-frame";
import { InitialSeal } from "../../../assets/ornaments/seal";

/* Cartiglio rientrato a destra — OrnateFrame small con sigillo iniziale PG + azione */
export default function PlayerAction({ action }: { action: string }) {
  const heroName = useGameStore((s) => s.campaign?.character_data?.name ?? "Hero");

  return (
    <div className="my-5 ml-auto max-w-[50ch]">
      <OrnateFrame variant="small" color="var(--gold-deep)">
        <div
          className="px-1 py-1"
          style={{ background: "var(--parchment-shadow)" }}
        >
          {/* Header: sigillo + "{name} acts:" */}
          <div className="flex items-center gap-2 mb-2">
            <InitialSeal name={heroName} size={24} />
            <span
              className="font-display text-[9px] uppercase"
              style={{ color: "var(--gold-deep)", letterSpacing: "0.2em" }}
            >
              {heroName} acts:
            </span>
          </div>
          <p className="font-body italic text-lg" style={{ color: "var(--ink-primary)" }}>
            {action}
          </p>
        </div>
      </OrnateFrame>
    </div>
  );
}
