import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCampaign, getTurns } from "../services/api";
import { useGameStore } from "../stores/game-store";
import { useUIStore } from "../stores/ui-store";
import NarrativeStream from "./narrative/narrative-stream";
import ActionInput from "./input/action-input";
import CharacterSheet from "./character/character-sheet";
import CompanionBar from "./companion/companion-bar";
import CombatTracker from "./combat/combat-tracker";
import type { CombatState, TurnResponse } from "../types";

export default function GameView() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();

  const setCampaign = useGameStore((s) => s.setCampaign);
  const setTurnHistory = useGameStore((s) => s.setTurnHistory);
  const campaign = useGameStore((s) => s.campaign);
  const addTurn = useGameStore((s) => s.addTurn);
  const setLoading = useGameStore((s) => s.setLoading);
  const setPendingAction = useGameStore((s) => s.setPendingAction);
  const setCurrentMood = useGameStore((s) => s.setCurrentMood);
  const setCombatState = useGameStore((s) => s.setCombatState);
  const updateWorldState = useGameStore((s) => s.updateWorldState);
  const updateCharacter = useGameStore((s) => s.updateCharacter);
  const updateTurnNumber = useGameStore((s) => s.updateTurnNumber);
  const currentMood = useGameStore((s) => s.currentMood);
  const combatState = useGameStore((s) => s.combatState);
  const isLoading = useGameStore((s) => s.isLoading);

  const [actionError, setActionError] = useState<string | null>(null);

  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { isLoading: isCampaignLoading } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId!).then((r) => r.data),
    enabled: !!campaignId,
  });

  // Initial load: campaign + turn history
  useEffect(() => {
    if (!campaignId) return;
    getCampaign(campaignId).then((r) => {
      setCampaign(r.data);
      // Restore combat state from persisted world_state
      const cs = r.data.world_state?.combat_state as CombatState | undefined;
      if (cs?.active) setCombatState(cs);
    });
    getTurns(campaignId).then((r) => {
      if (r.data?.length) {
        setTurnHistory([...r.data].reverse() as TurnResponse[]);
      }
    });
  }, [campaignId, setCampaign, setTurnHistory, setCombatState]);

  // Called by ActionInput when the player submits an action
  const handleAction = async (action: string) => {
    if (!campaignId || isLoading) return;

    setActionError(null);
    setPendingAction(action);
    setLoading(true);

    // Scroll down so skeleton loader is visible
    requestAnimationFrame(() => {
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    });

    try {
      const { submitAction } = await import("../services/api");
      const res = await submitAction(campaignId, action);
      const turn = res.data;

      addTurn(turn);

      // Update store with backend state
      if (turn.world_state) updateWorldState(turn.world_state as never);
      if (turn.character_data) updateCharacter(turn.character_data as never);
      if (turn.turn_number) updateTurnNumber(turn.turn_number);
      if (turn.scene_mood) setCurrentMood(turn.scene_mood);

      // Combat state
      if (turn.combat_state?.active) {
        setCombatState(turn.combat_state);
      } else if (turn.combat_state && !turn.combat_state.active) {
        setCombatState(null);
      }
    } catch (err) {
      console.error("Action failed", err);
      setActionError("The DM couldn't process your action. Please try again.");
    } finally {
      setLoading(false);
      setPendingAction(null);
    }
  };

  if (isCampaignLoading || !campaign) {
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
              className="rounded px-2 py-1 text-sm text-parchment-400 hover:bg-parchment-800 hover:text-parchment-200"
              title="Back to campaigns"
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
                    &mdash; Day {campaign.world_state.clock.current_day},{" "}
                    {campaign.world_state.clock.time_of_day}
                  </>
                )}
                {campaign.world_state?.meta?.current_season && (
                  <> &mdash; {campaign.world_state.meta.current_season}</>
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
