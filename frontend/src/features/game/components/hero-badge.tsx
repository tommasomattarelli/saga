import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";

export default function HeroBadge() {
  const { t } = useTranslation();
  const char = useGameStore((s) => s.campaign?.character_data);
  if (!char?.name) return null;
  const hp = char.hp ?? { current: 0, max: 0 };
  const hpPct = hp.max > 0 ? Math.max(0, Math.min(100, (hp.current / hp.max) * 100)) : 0;

  return (
    <div className="flex items-center gap-3 min-w-0">
      <div
        aria-hidden="true"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-sm font-semibold"
        style={{
          border: "1px solid var(--line-strong)",
          color: "var(--accent)",
          background: "var(--parchment-base)",
        }}
      >
        {char.name[0]?.toUpperCase()}
      </div>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span
            className="font-display text-sm font-semibold truncate"
            style={{ color: "var(--ink-primary)" }}
          >
            {char.name}
          </span>
          <span className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
            {t("game.level_abbr")} {char.level}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <div
            aria-label={`HP ${hp.current} of ${hp.max}`}
            className="h-1 w-20 overflow-hidden rounded-full"
            style={{ background: "var(--line)" }}
          >
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${hpPct}%`, background: "var(--blood)" }}
            />
          </div>
          <span className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
            {hp.current}/{hp.max}
          </span>
        </div>
      </div>
    </div>
  );
}
