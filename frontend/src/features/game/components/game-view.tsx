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
  const { mutation, scrollRef: submitScrollRef } = useSubmitAction(campaignId!);

  // Sync scrollRef to the one inside useSubmitAction
  submitScrollRef.current = scrollRef.current;

  const [actionError, setActionError] = useState<string | null>(null);

  const handleAction = async (action: string) => {
    setActionError(null);
    try {
      await mutation.mutateAsync(action);
    } catch {
      setActionError("The DM couldn't process your action. Please try again.");
    }
  };

  if (isDataLoading || !campaign) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-parchment-400">Loading your adventure…</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen" data-mood={currentMood}>
      {combatState?.active && <CombatTracker combatState={combatState} />}

      <div className="mood-container flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-parchment-700/20 bg-parchment-900/90 px-4 py-2">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/")}
              aria-label="Back to campaigns"
              className="rounded px-2 py-1 text-sm text-parchment-400 hover:bg-parchment-800 hover:text-parchment-200"
            >
              &larr;
            </button>
            <div>
              <h2 className="font-display text-lg text-gold-400">{campaign.name}</h2>
              <span className="text-xs text-parchment-500">
                Turn {campaign.turn_number} &mdash;{" "}
                {campaign.world_state?.location || "Unknown location"}
                {campaign.world_state?.clock && (
                  <>
                    {" "}
                    &mdash; Day {(campaign.world_state.clock as Record<string, unknown>).current_day as number},{" "}
                    {(campaign.world_state.clock as Record<string, unknown>).time_of_day as string}
                  </>
                )}
              </span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => toggleSidePanel("character")}
              className="rounded px-3 py-1 text-sm text-parchment-300 hover:bg-parchment-800"
            >
              Character
            </button>
            <button
              onClick={() => toggleSidePanel("quests")}
              className="rounded px-3 py-1 text-sm text-parchment-300 hover:bg-parchment-800"
            >
              Quests
            </button>
            <button
              onClick={() => toggleSidePanel("settings")}
              className="rounded px-3 py-1 text-sm text-parchment-300 hover:bg-parchment-800"
            >
              Settings
            </button>
          </div>
        </header>

        <CompanionBar />

        <div ref={scrollRef} className="narrative-scroll flex-1 overflow-y-auto px-6 py-4">
          <NarrativeStream scrollRef={scrollRef} actionError={actionError} />
        </div>

        <ActionInput campaignId={campaign.id} onAction={handleAction} />
      </div>

      {sidePanel && (
        <aside className="w-80 overflow-y-auto border-l border-parchment-700/20 bg-parchment-900/95 p-4">
          {sidePanel === "character" && <CharacterSheet />}
          {sidePanel === "quests" && (
            <div>
              <h3 className="mb-3 font-display text-lg text-gold-400">Active Quests</h3>
              {(campaign.quests?.active as Array<{ name: string; description: string }> | undefined)?.map(
                (q, i) => (
                  <div key={i} className="mb-2 rounded border border-parchment-700/20 p-3">
                    <p className="font-semibold text-parchment-200">{q.name}</p>
                    <p className="text-sm text-parchment-400">{q.description}</p>
                  </div>
                ),
              ) || <p className="text-sm text-parchment-500">No active quests</p>}
            </div>
          )}
          {sidePanel === "settings" && (
            <div>
              <h3 className="mb-3 font-display text-lg text-gold-400">Settings</h3>
              <p className="text-sm text-parchment-400">Settings panel (WIP)</p>
            </div>
          )}
        </aside>
      )}
    </div>
  );
}
