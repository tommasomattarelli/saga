import { useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCampaign } from "../services/api";
import { GameWebSocket } from "../services/websocket";
import { useGameStore } from "../stores/game-store";
import { useUIStore } from "../stores/ui-store";
import NarrativeStream from "./narrative/narrative-stream";
import ActionInput from "./input/action-input";
import CharacterSheet from "./character/character-sheet";
import CompanionBar from "./companion/companion-bar";
import type { DiceRollResult } from "../types";

export default function GameView() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const setCampaign = useGameStore((s) => s.setCampaign);
  const campaign = useGameStore((s) => s.campaign);
  const addTurn = useGameStore((s) => s.addTurn);
  const setProcessing = useGameStore((s) => s.setProcessing);
  const setStreaming = useGameStore((s) => s.setStreaming);
  const appendNarration = useGameStore((s) => s.appendNarration);
  const setPendingDice = useGameStore((s) => s.setPendingDice);
  const resetStreaming = useGameStore((s) => s.resetStreaming);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);
  const currentMood = useGameStore((s) => s.streaming.currentMood);

  const wsRef = useRef<GameWebSocket | null>(null);

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

  // WebSocket lifecycle
  useEffect(() => {
    if (!campaignId) return;

    const ws = new GameWebSocket(campaignId);
    wsRef.current = ws;

    ws.on("turn_start", () => {
      setProcessing(true);
      resetStreaming();
      setStreaming({ isStreaming: true });
    });

    ws.on("narration", (data) => {
      appendNarration(data.text as string);
    });

    ws.on("dm:narration:chunk", (data) => {
      appendNarration(data.chunk as string);
    });

    ws.on("dice_rolls", (data) => {
      setPendingDice(data.rolls as Record<string, DiceRollResult>);
    });

    ws.on("dice:roll", (data) => {
      const roll = data as unknown as Record<string, DiceRollResult>;
      setPendingDice(roll);
    });

    ws.on("dice:narration:chunk", (data) => {
      appendNarration(data.chunk as string);
    });

    ws.on("scene_mood", (data) => {
      setStreaming({ currentMood: (data.mood as string) || "neutral" });
    });

    ws.on("turn_complete", (data) => {
      setProcessing(false);
      setStreaming({ isStreaming: false });

      const turnData = data as Record<string, unknown>;
      const state = useGameStore.getState();
      addTurn({
        turn_number: turnData.turn_number as number,
        narration: state.streaming.currentNarration || (turnData.narration as string) || "",
        dice_rolls:
          (turnData.dice_rolls as Record<string, DiceRollResult>) || state.streaming.pendingDice,
        companion_actions: (turnData.companion_actions as Record<string, string>) || null,
        world_updates: (turnData.world_updates as Record<string, unknown>) || null,
        scene_mood: (turnData.scene_mood as string) || state.streaming.currentMood,
        suggested_actions: (turnData.suggested_actions as string[]) || null,
        model_used: (turnData.model_used as string) || "",
        invoke_npcs: (turnData.invoke_npcs as string[]) || [],
        time_passed_minutes: (turnData.time_passed_minutes as number) || 5,
        ambient_detail: (turnData.ambient_detail as string) || null,
        requires_player_action: (turnData.requires_player_action as boolean) ?? true,
      });

      resetStreaming();
    });

    ws.connect();

    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, [
    campaignId,
    addTurn,
    setProcessing,
    setStreaming,
    appendNarration,
    setPendingDice,
    resetStreaming,
  ]);

  if (isLoading || !campaign) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-parchment-400">Loading your adventure...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen" data-mood={currentMood}>
      <div className="mood-container flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-parchment-700/20 bg-parchment-900/90 px-4 py-2">
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
          <NarrativeStream wsRef={wsRef} />
        </div>

        <ActionInput campaignId={campaign.id} wsRef={wsRef} />
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
