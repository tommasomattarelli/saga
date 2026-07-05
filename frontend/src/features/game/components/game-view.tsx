import { useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";

import { useCampaignData } from "../hooks/use-campaign-data";
import { useSubmitAction } from "../hooks/use-submit-action";
import NarrativeStream from "../../narrative/components/narrative-stream";
import ActionInput from "./action-input";
import CharacterSheet from "../../character/components/character-sheet";
import CompanionBar from "../../character/components/companion-bar";
import CombatTracker from "../../combat/components/combat-tracker";
import JournalDrawer from "./journal-drawer";
import SettingsDrawer from "./settings-drawer";
// CharacterSheet manages its own fullscreen modal dialog internally

/* Avatar disc + name / level / HP — the player identity cluster (ADR 0013 A4) */
function HeroBadge() {
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

export default function GameView() {
  const { t } = useTranslation();
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const campaign = useGameStore((s) => s.campaign);
  const combatState = useGameStore((s) => s.combatState);
  const hasTurns = useGameStore((s) => s.turnHistory.length > 0);

  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);

  const { isLoading: isDataLoading, error: dataError } = useCampaignData(campaignId);
  const { mutation } = useSubmitAction(campaignId!, scrollRef);

  const [actionError, setActionError] = useState<string | null>(null);

  const handleAction = async (action: string) => {
    setActionError(null);
    try {
      await mutation.mutateAsync(action);
    } catch (err) {
      setActionError(t("errors.action_failed"));
      throw err; // let ActionInput keep the typed text
    }
  };

  if (isDataLoading || !campaign) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--parchment-base)" }}
      >
        <p className="font-display text-sm" style={{ color: "var(--ink-secondary)" }}>
          {isDataLoading ? t("game.loading_campaign") : t("game.history_error")}
        </p>
      </div>
    );
  }

  const clock = campaign.world_state?.clock as
    | { current_day?: number; time_of_day?: string }
    | undefined;
  const location = campaign.world_state?.location as string | undefined;

  const panels = [
    { key: "character" as const, label: t("game.character") },
    { key: "quests" as const, label: t("game.journal") },
    { key: "settings" as const, label: t("game.settings") },
  ];

  return (
    <div className="flex h-screen" style={{ background: "var(--parchment-base)" }}>
      {/* CombatTracker handles its own AnimatePresence — always render when state exists */}
      {combatState && <CombatTracker combatState={combatState} />}

      <div
        className="flex flex-1 flex-col"
        style={combatState ? { paddingBottom: "150px" } : undefined}
      >
        <header
          className="px-6 py-3"
          style={{
            background: "var(--parchment-aged)",
            borderBottom: "1px solid var(--line)",
          }}
        >
          <div className="flex items-center justify-between gap-6">
            {/* Left: back + hero identity */}
            <div className="flex items-center gap-4 min-w-0 flex-1">
              <button
                onClick={() => navigate("/campaigns")}
                className="font-display text-sm shrink-0 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                style={{ color: "var(--ink-faded)" }}
              >
                ← {t("game.back_to_campaigns")}
              </button>
              <span aria-hidden="true" className="h-5 w-px" style={{ background: "var(--line)" }} />
              <HeroBadge />
            </div>

            {/* Center: campaign title + world meta */}
            <div className="text-center min-w-0">
              <h2
                className="font-display text-base font-semibold truncate"
                style={{ color: "var(--ink-primary)" }}
              >
                {campaign.name}
              </h2>
              <div className="font-display text-xs mt-0.5" style={{ color: "var(--ink-faded)" }}>
                <span>
                  {t("game.chapter")} {campaign.turn_number}
                </span>
                {location && <span> · {location}</span>}
                {clock?.current_day && (
                  <span>
                    {" "}
                    · {t("game.day")} {clock.current_day}
                    {clock.time_of_day && `, ${clock.time_of_day}`}
                  </span>
                )}
              </div>
            </div>

            {/* Right: labeled panel pills */}
            <nav className="flex gap-2 justify-end flex-1">
              {panels.map((p) => {
                const active = sidePanel === p.key;
                return (
                  <button
                    key={p.key}
                    onClick={() => toggleSidePanel(p.key)}
                    aria-pressed={active}
                    className="rounded-full px-3.5 py-1.5 font-display text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                    style={{
                      border: `1px solid ${active ? "var(--accent)" : "var(--line-strong)"}`,
                      color: active ? "var(--accent)" : "var(--ink-secondary)",
                    }}
                  >
                    {p.label}
                  </button>
                );
              })}
            </nav>
          </div>
        </header>

        <CompanionBar />

        <main
          id="main-content"
          ref={scrollRef}
          className="narrative-scroll flex-1 overflow-y-auto px-8 py-8"
          style={{ background: "var(--parchment-base)" }}
        >
          <div className="mx-auto" style={{ maxWidth: "68ch" }}>
            {dataError && (
              <div
                role="alert"
                className="mb-6 rounded-md px-4 py-3 font-display text-sm"
                style={{
                  border: "1px solid var(--blood-dark)",
                  color: "var(--blood)",
                }}
              >
                {t("game.history_error")}
              </div>
            )}
            {/* on a failed history load don't render the misleading "not started yet" empty state */}
            {(!dataError || hasTurns) && (
              <NarrativeStream scrollRef={scrollRef} actionError={actionError} />
            )}
          </div>
        </main>

        <ActionInput onAction={handleAction} />
      </div>

      {/* Character sheet — fullscreen modal (self-contained) */}
      <CharacterSheet />

      {/* Dedicated drawer components (self-contained with Radix Dialog) */}
      <JournalDrawer />
      <SettingsDrawer />
    </div>
  );
}
