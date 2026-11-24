import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";

import { useCampaignData } from "../hooks/use-campaign-data";
import { useSubmitAction } from "../hooks/use-submit-action";
import { retryCampaignMemory } from "../../../shared/api/client";
import { useEnsureEmbeddingIndex } from "../hooks/use-ensure-embedding-index";
import NarrativeStream from "../../narrative/components/narrative-stream";
import ActionInput from "./action-input";
import ActionErrorBanner from "./action-error-banner";
import HeroBadge from "./hero-badge";
import CharacterSheet from "../../character/components/character-sheet";
import CompanionBar from "../../character/components/companion-bar";
import SceneLifeBars, { npcsInScene } from "../../scene/components/scene-life-bars";
import JournalDrawer from "./journal-drawer";
import SettingsDrawer from "./settings-drawer";
import WorldMap from "../../map/components/world-map";
// CharacterSheet manages its own fullscreen modal dialog internally

export default function GameView() {
  const { t } = useTranslation();
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const campaign = useGameStore((s) => s.campaign);
  const hasTurns = useGameStore((s) => s.turnHistory.length > 0);
  const sceneIsPopulated = npcsInScene(campaign?.world_state).length > 0;

  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);

  const { isLoading: isDataLoading, error: dataError } = useCampaignData(campaignId);
  useEnsureEmbeddingIndex(campaignId);
  const { submit, actionReady } = useSubmitAction(campaignId!, scrollRef);

  const [actionError, setActionError] = useState<string | null>(null);
  const [memoryRetryRequired, setMemoryRetryRequired] = useState(false);
  const retryRef = useRef<{
    action: string;
    requestId: string;
    head: string | null;
    epoch: number;
  } | null>(null);

  useEffect(() => {
    retryRef.current = null;
  }, [campaignId]);

  const handleAction = async (action: string) => {
    setActionError(null);
    try {
      const retry = retryRef.current?.action === action ? retryRef.current : null;
      const requestId = retry?.requestId ?? crypto.randomUUID();
      const context = retry ?? {
        action,
        requestId,
        head: campaign?.active_head_turn_id ?? null,
        epoch: campaign?.context_epoch ?? 0,
      };
      retryRef.current = context;
      await submit(action, requestId, { head: context.head, epoch: context.epoch });
      retryRef.current = null;
      setMemoryRetryRequired(false);
    } catch (err) {
      const code = isAxiosError<{ detail?: { code?: string } }>(err)
        ? err.response?.data?.detail?.code
        : undefined;
      const status = isAxiosError(err) ? err.response?.status : undefined;
      if (
        code === "action_interrupted" ||
        code === "action_timeout" ||
        code === "action_context_changed" ||
        status === 422 ||
        status === 500 ||
        status === 502
      ) {
        retryRef.current = null;
      }
      setMemoryRetryRequired(
        code === "memory_retry_required" || code === "memory_configuration_required",
      );
      setActionError(
        t(
          code === "memory_busy"
            ? "errors.memory_busy"
            : code === "memory_retry_required"
              ? "errors.memory_retry_required"
              : code === "memory_configuration_required"
                ? "errors.memory_configuration_required"
                : code === "action_in_progress"
                  ? "errors.action_in_progress"
                  : code === "action_context_changed"
                    ? "errors.action_context_changed"
                    : code === "campaign_history_required"
                      ? "errors.campaign_history_required"
                      : "errors.action_failed",
        ),
      );
      throw err; // let ActionInput keep the typed text
    }
  };

  const handleMemoryRetry = async () => {
    const pending = retryRef.current;
    if (!pending) return;
    try {
      await retryCampaignMemory(campaign!.id, pending.head, pending.epoch);
    } catch {
      setActionError(t("errors.memory_retry_failed"));
      return;
    }
    await handleAction(pending.action).catch(() => undefined);
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
    { key: "map" as const, label: t("game.map") },
    { key: "quests" as const, label: t("game.journal") },
    { key: "settings" as const, label: t("game.settings") },
  ];

  return (
    <div className="flex h-screen" style={{ background: "var(--parchment-base)" }}>
      {/* ADR 0003 B2 — the scene always shows who is standing here, fight or none */}
      <SceneLifeBars worldState={campaign.world_state} />

      <div
        className="flex flex-1 flex-col"
        style={sceneIsPopulated ? { paddingBottom: "150px" } : undefined}
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
            <ActionErrorBanner
              actionError={actionError}
              historyError={!!dataError}
              memoryRetryRequired={memoryRetryRequired && !!retryRef.current}
              onMemoryRetry={() => void handleMemoryRetry()}
            />
            {/* on a failed history load don't render the misleading "not started yet" empty state */}
            {(!dataError || hasTurns) && (
              <NarrativeStream scrollRef={scrollRef} actionError={actionError} />
            )}
          </div>
        </main>

        <ActionInput onAction={handleAction} disabled={!actionReady} />
      </div>

      {/* Character sheet — fullscreen modal (self-contained) */}
      <CharacterSheet />

      {/* Dedicated drawer components (self-contained with Radix Dialog) */}
      <JournalDrawer />
      <SettingsDrawer />

      {/* Read-only world map (ADR 0008 B4) */}
      {campaignId && <WorldMap campaignId={campaignId} />}
    </div>
  );
}
