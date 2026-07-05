import { useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
import { OrnamentDivider } from "../../../shared/ui/ornament-divider";
// CharacterSheet manages its own fullscreen modal dialog internally

export default function GameView() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const campaign = useGameStore((s) => s.campaign);
  const currentMood = useGameStore((s) => s.currentMood);
  const combatState = useGameStore((s) => s.combatState);

  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);

  const { isLoading: isDataLoading } = useCampaignData(campaignId);
  const { mutation } = useSubmitAction(campaignId!, scrollRef);

  const [actionError, setActionError] = useState<string | null>(null);

  const handleAction = async (action: string) => {
    setActionError(null);
    try {
      await mutation.mutateAsync(action);
    } catch {
      setActionError("The DM's quill falters. Try thy action anew.");
    }
  };

  if (isDataLoading || !campaign) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--parchment-base)" }}
      >
        <p className="font-body italic text-lg" style={{ color: "var(--ink-secondary)" }}>
          The chronicler retrieves thy tale…
        </p>
      </div>
    );
  }

  const clock = campaign.world_state?.clock as
    | { current_day?: number; time_of_day?: string }
    | undefined;
  const location = (campaign.world_state?.location as string | undefined) || "Unknown lands";

  return (
    <div
      className="flex h-screen"
      data-mood={currentMood}
      style={{ background: "var(--parchment-base)" }}
    >
      {/* CombatTracker handles its own AnimatePresence — always render when state exists */}
      {combatState && <CombatTracker combatState={combatState} />}

      <div
        className="mood-container flex flex-1 flex-col"
        style={combatState ? { paddingBottom: "150px" } : undefined}
      >
        {/* Ornamental banner header */}
        <header
          className="relative px-6 pt-3 pb-1"
          style={{
            background: "var(--parchment-aged)",
            borderBottom: "1px solid var(--gold-deep)",
          }}
        >
          <div className="flex items-center justify-between gap-4">
            <button
              onClick={() => navigate("/campaigns")}
              aria-label="Back to the shelf"
              className="font-display text-xs uppercase px-2 py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
              style={{
                color: "var(--ink-faded)",
                letterSpacing: "0.25em",
              }}
            >
              ← Shelf
            </button>

            <div className="flex-1 text-center">
              <h2
                className="font-display text-lg uppercase truncate"
                style={{
                  color: "var(--gold-bright)",
                  letterSpacing: "0.22em",
                }}
              >
                {campaign.name}
              </h2>
              <div
                className="font-display text-[10px] uppercase mt-0.5"
                style={{ color: "var(--ink-faded)", letterSpacing: "0.28em" }}
              >
                <span>Chapter {campaign.turn_number}</span>
                <span className="mx-2" aria-hidden="true">
                  ·
                </span>
                <span
                  className="italic normal-case"
                  style={{ fontStyle: "italic", letterSpacing: "0.1em" }}
                >
                  {location}
                </span>
                {clock?.current_day && (
                  <>
                    <span className="mx-2" aria-hidden="true">
                      ·
                    </span>
                    <span>Day {clock.current_day}</span>
                    {clock.time_of_day && (
                      <>
                        <span className="mx-2" aria-hidden="true">
                          ·
                        </span>
                        <span>{clock.time_of_day}</span>
                      </>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* Action toolbar — rune-style buttons */}
            <div className="flex gap-1">
              {[
                { key: "character" as const, glyph: "❖", label: "Character" },
                { key: "quests" as const, glyph: "✦", label: "Quests" },
                { key: "settings" as const, glyph: "⚙", label: "Settings" },
              ].map((t) => {
                const active = sidePanel === t.key;
                return (
                  <button
                    key={t.key}
                    onClick={() => toggleSidePanel(t.key)}
                    aria-label={t.label}
                    title={t.label}
                    className="w-9 h-9 flex items-center justify-center transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
                    style={{
                      border: `1px solid ${active ? "var(--gold-bright)" : "var(--gold-deep)"}`,
                      background: active ? "rgba(212, 175, 55, 0.15)" : "transparent",
                      color: active ? "var(--gold-bright)" : "var(--ink-secondary)",
                      fontFamily: "var(--font-display)",
                      fontSize: 16,
                    }}
                  >
                    {t.glyph}
                  </button>
                );
              })}
            </div>
          </div>
          <OrnamentDivider variant="flourish-b" className="!my-1" />
        </header>

        <CompanionBar />

        <main
          id="main-content"
          ref={scrollRef}
          className="narrative-scroll flex-1 overflow-y-auto px-8 py-6"
          style={{ background: "var(--parchment-base)" }}
        >
          <div className="mx-auto max-w-3xl">
            <NarrativeStream scrollRef={scrollRef} actionError={actionError} />
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
