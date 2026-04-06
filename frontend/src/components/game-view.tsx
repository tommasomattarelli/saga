import { useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCampaign, getTurns } from "../services/api";
import { GameWebSocket } from "../services/websocket";
import { useGameStore, setDiceRevealCallback } from "../stores/game-store";
import { useUIStore } from "../stores/ui-store";
import NarrativeStream from "./narrative/narrative-stream";
import ActionInput from "./input/action-input";
import CharacterSheet from "./character/character-sheet";
import CompanionBar from "./companion/companion-bar";
import CombatTracker from "./combat/combat-tracker";
import type {
  CharacterData,
  CombatState,
  DeathEvent,
  DiceRollResult,
  TurnResponse,
  WorldState,
} from "../types";

export default function GameView() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const setCampaign = useGameStore((s) => s.setCampaign);
  const setTurnHistory = useGameStore((s) => s.setTurnHistory);
  const campaign = useGameStore((s) => s.campaign);
  const addTurn = useGameStore((s) => s.addTurn);
  const setProcessing = useGameStore((s) => s.setProcessing);
  const setStreaming = useGameStore((s) => s.setStreaming);
  const appendNarration = useGameStore((s) => s.appendNarration);
  const setPendingDice = useGameStore((s) => s.setPendingDice);
  const resetStreaming = useGameStore((s) => s.resetStreaming);
  const updateWorldState = useGameStore((s) => s.updateWorldState);
  const updateCharacter = useGameStore((s) => s.updateCharacter);
  const updateTurnNumber = useGameStore((s) => s.updateTurnNumber);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);
  const currentMood = useGameStore((s) => s.streaming.currentMood);
  const deathEvent = useGameStore((s) => s.streaming.deathEvent);
  const persistentCombat = campaign?.world_state?.combat_state;

  const wsRef = useRef<GameWebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { isLoading } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => getCampaign(campaignId!).then((r) => r.data),
    enabled: !!campaignId,
  });

  useEffect(() => {
    if (!campaignId) return;
    getCampaign(campaignId).then((r) => {
      setCampaign(r.data);
    });
    getTurns(campaignId).then((r) => {
      if (r.data?.length) {
        // Journal returns newest-first; reverse to chronological order
        setTurnHistory([...r.data].reverse() as TurnResponse[]);
      }
    });
  }, [campaignId, setCampaign, setTurnHistory]);

  // WebSocket lifecycle
  const isMountedRef = useRef(true);
  useEffect(() => {
    if (!campaignId) return;
    isMountedRef.current = true;

    const ws = new GameWebSocket(campaignId);
    wsRef.current = ws;

    const guard =
      <T extends unknown[]>(fn: (...args: T) => void) =>
      (...args: T) => {
        if (isMountedRef.current) fn(...args);
      };

    ws.on(
      "turn_start",
      guard(() => {
        const currentAction = useGameStore.getState().streaming.pendingAction;
        setProcessing(true);
        resetStreaming();
        setStreaming({ isStreaming: true, pendingAction: currentAction });
      }),
    );

    ws.on(
      "narration",
      guard((data) => {
        appendNarration(data.text as string);
      }),
    );

    ws.on(
      "dm:narration:chunk",
      guard((data) => {
        appendNarration(data.chunk as string);
      }),
    );

    ws.on(
      "dice_rolls",
      guard((data) => {
        setPendingDice(data.rolls as Record<string, DiceRollResult>);
      }),
    );

    ws.on(
      "dice:roll",
      guard((data) => {
        const { type: _, ...rolls } = data;
        setPendingDice(rolls as Record<string, DiceRollResult>);
        setStreaming({ diceAwaitingReveal: true });
      }),
    );

    // Server paused — player must click to reveal dice
    ws.on(
      "await:dice_reveal",
      guard(() => {
        setStreaming({ diceAwaitingReveal: true });
      }),
    );

    ws.on(
      "scene_mood",
      guard((data) => {
        setStreaming({ currentMood: (data.mood as string) || "neutral" });
      }),
    );

    ws.on(
      "combat:start",
      guard((data) => {
        setStreaming({ combatState: data as unknown as CombatState });
      }),
    );

    ws.on(
      "combat:end",
      guard(() => {
        setStreaming({ combatState: null });
      }),
    );

    // Visible tool execution events
    ws.on(
      "tool:executed",
      guard((data) => {
        const toolData = data as Record<string, unknown>;
        const toolName = toolData.tool as string;

        if (toolName === "update_hp" || toolName === "apply_damage") {
          // CharacterSheet and CombatTracker update automatically from turn_complete
          // For immediate visual feedback, could trigger a flash here
        }
        if (toolName === "add_item" || toolName === "remove_item") {
          // Could show a toast notification here in a future sprint
        }
      }),
    );

    ws.on(
      "death:event",
      guard((data) => {
        setStreaming({ deathEvent: data as unknown as DeathEvent });
      }),
    );

    ws.on(
      "error",
      guard(() => {
        setProcessing(false);
        setStreaming({ isStreaming: false });
      }),
    );

    ws.on(
      "turn_complete",
      guard((data) => {
        setProcessing(false);
        setStreaming({ isStreaming: false });

        const turnData = data as Record<string, unknown>;
        const state = useGameStore.getState();
        addTurn({
          turn_number: turnData.turn_number as number,
          player_action: (turnData.player_action as string) || undefined,
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

        // Sync backend state into store so CharacterSheet, CombatTracker, etc. update
        const worldState = turnData.world_state as WorldState | undefined;
        const characterData = turnData.character_data as CharacterData | undefined;
        if (worldState) updateWorldState(worldState);
        if (characterData) updateCharacter(characterData);
        if (turnData.turn_number) updateTurnNumber(turnData.turn_number as number);

        resetStreaming();
      }),
    );

    // Register dice reveal callback — sends dice_revealed to server when player clicks
    setDiceRevealCallback(() => {
      wsRef.current?.send({ type: "dice_revealed" });
    });

    ws.connect();

    return () => {
      isMountedRef.current = false;
      setDiceRevealCallback(null);
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
    updateWorldState,
    updateCharacter,
    updateTurnNumber,
  ]);

  if (isLoading || !campaign) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-parchment-400">Loading your adventure...</p>
      </div>
    );
  }

  const deathOverlayMessage = deathEvent
    ? deathEvent.mode === "cronista"
      ? {
          title: "Near Death!",
          sub: "You survive by a thread — your story is not over yet.",
          color: "text-yellow-400",
        }
      : deathEvent.mode === "destino"
        ? {
            title: "Fate Intervenes!",
            sub: deathEvent.cost_hint || "Destiny has a price.",
            color: "text-purple-400",
          }
        : { title: "You Have Fallen", sub: "Your journey ends here.", color: "text-red-500" }
    : null;

  return (
    <div className="flex h-screen" data-mood={currentMood}>
      {persistentCombat?.active && <CombatTracker combatState={persistentCombat} />}

      {deathEvent && deathOverlayMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
          <div className="max-w-md rounded-lg border border-parchment-700/30 bg-parchment-900 p-8 text-center shadow-2xl">
            <h2 className={`mb-3 font-display text-4xl font-bold ${deathOverlayMessage.color}`}>
              {deathOverlayMessage.title}
            </h2>
            <p className="mb-6 text-parchment-300">{deathOverlayMessage.sub}</p>
            {deathEvent.mode !== "ironman" && (
              <button
                onClick={() => setStreaming({ deathEvent: null })}
                className="rounded bg-gold-600 px-6 py-2 text-sm font-semibold text-parchment-900 hover:bg-gold-500"
              >
                Continue
              </button>
            )}
          </div>
        </div>
      )}

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
          <NarrativeStream wsRef={wsRef} scrollRef={scrollRef} />
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
