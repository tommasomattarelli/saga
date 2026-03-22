import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCampaign } from "../services/api";
import { useGameStore } from "../stores/game-store";
import { useUIStore } from "../stores/ui-store";
import NarrativeStream from "./narrative/narrative-stream";
import ActionInput from "./input/action-input";
import CharacterSheet from "./character/character-sheet";
import CompanionBar from "./companion/companion-bar";

export default function GameView() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const setCampaign = useGameStore((s) => s.setCampaign);
  const campaign = useGameStore((s) => s.campaign);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);

  const { isLoading } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId!).then((r) => r.data),
    enabled: !!campaignId,
  });

  useEffect(() => {
    if (campaignId) {
      getCampaign(campaignId).then((r) => setCampaign(r.data));
    }
  }, [campaignId, setCampaign]);

  if (isLoading || !campaign) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-parchment-400">Loading your adventure...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-parchment-700/20 bg-parchment-900/90 px-4 py-2">
          <div>
            <h2 className="font-display text-lg text-gold-400">{campaign.name}</h2>
            <span className="text-xs text-parchment-500">
              Turn {campaign.turn_number} &mdash;{" "}
              {campaign.world_state?.location || "Unknown location"}
            </span>
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

        <div className="narrative-scroll flex-1 overflow-y-auto px-6 py-4">
          <NarrativeStream />
        </div>

        <ActionInput campaignId={campaign.id} />
      </div>

      {sidePanel && (
        <aside className="w-80 overflow-y-auto border-l border-parchment-700/20 bg-parchment-900/95 p-4">
          {sidePanel === "character" && <CharacterSheet />}
          {sidePanel === "quests" && (
            <div>
              <h3 className="mb-3 font-display text-lg text-gold-400">Active Quests</h3>
              {campaign.quests?.active?.map(
                (q: { name: string; description: string }, i: number) => (
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
