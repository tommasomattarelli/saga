import { create } from "zustand";
import type {
  Campaign,
  TurnResponse,
  WorldState,
  CharacterData,
  DiceRollResult,
  CombatState,
  DeathEvent,
  NarrationSegment,
  NPCDialogue,
} from "../types";

const ALLOWED_WORLD_STATE_KEYS = new Set([
  "meta",
  "locations",
  "factions",
  "npcs",
  "companions",
  "time_of_day",
  "weather",
  "global_flags",
  "clock",
  "combat_state",
  "destino_lives",
]);

// Module-level callback for dice reveal — set by game-view, called by DiceRoller
let diceRevealCallback: (() => void) | null = null;
export function setDiceRevealCallback(cb: (() => void) | null): void {
  diceRevealCallback = cb;
}

const __DEV__ =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

interface StreamingState {
  isStreaming: boolean;
  currentNarration: string;
  segments: NarrationSegment[];
  pendingDice: Record<string, DiceRollResult> | null;
  diceRevealed: boolean;
  diceAwaitingReveal: boolean; // server paused, waiting for player to click
  currentMood: string;
  combatState: CombatState | null;
  deathEvent: DeathEvent | null;
  pendingAction: string | null;
}

interface GameState {
  campaign: Campaign | null;
  turnHistory: TurnResponse[];
  isProcessing: boolean;
  streaming: StreamingState;
  setCampaign: (campaign: Campaign) => void;
  setTurnHistory: (turns: TurnResponse[]) => void;
  addTurn: (turn: TurnResponse) => void;
  setPendingAction: (action: string | null) => void;
  setProcessing: (processing: boolean) => void;
  updateWorldState: (updates: Partial<WorldState>) => void;
  updateCharacter: (updates: Partial<CharacterData>) => void;
  updateTurnNumber: (n: number) => void;
  setStreaming: (updates: Partial<StreamingState>) => void;
  appendNarration: (chunk: string, stepIndex?: number) => void;
  appendSegmentDice: (dice: Record<string, DiceRollResult>, stepIndex: number) => void;
  appendSegmentNpc: (npc: NPCDialogue, stepIndex: number) => void;
  setPendingDice: (dice: Record<string, DiceRollResult>) => void;
  revealDice: () => void;
  resetStreaming: () => void;
  reset: () => void;
}

const initialStreaming: StreamingState = {
  isStreaming: false,
  currentNarration: "",
  segments: [],
  pendingDice: null,
  diceRevealed: false,
  diceAwaitingReveal: false,
  currentMood: "neutral",
  combatState: null,
  deathEvent: null,
  pendingAction: null,
};

function upsertSegment(
  segments: NarrationSegment[],
  stepIndex: number,
  mutate: (seg: NarrationSegment) => NarrationSegment,
): NarrationSegment[] {
  const idx = segments.findIndex((s) => s.step === stepIndex);
  if (idx === -1) {
    const fresh: NarrationSegment = { step: stepIndex, text: "", dice: null, npc_dialogues: [] };
    return [...segments, mutate(fresh)].sort((a, b) => a.step - b.step);
  }
  const next = segments.slice();
  next[idx] = mutate(next[idx]);
  return next;
}

export const useGameStore = create<GameState>()((set) => ({
  campaign: null,
  turnHistory: [],
  isProcessing: false,
  streaming: { ...initialStreaming },
  setCampaign: (campaign) => set({ campaign }),
  setTurnHistory: (turns) => set({ turnHistory: turns }),
  addTurn: (turn) => set((state) => ({ turnHistory: [...state.turnHistory, turn] })),
  setPendingAction: (action) =>
    set((state) => ({ streaming: { ...state.streaming, pendingAction: action } })),
  setProcessing: (processing) => set({ isProcessing: processing }),
  updateWorldState: (updates) =>
    set((state) => {
      if (__DEV__) {
        const leaked = Object.keys(updates).filter((k) => !ALLOWED_WORLD_STATE_KEYS.has(k));
        if (leaked.length > 0) {
          console.warn("[game-store] WorldState leakage (UI keys found):", leaked);
        }
      }

      if (!state.campaign) return state;
      return {
        campaign: {
          ...state.campaign,
          world_state: { ...state.campaign.world_state, ...updates },
        },
      };
    }),
  updateCharacter: (updates) =>
    set((state) => {
      if (!state.campaign) return state;
      return {
        campaign: {
          ...state.campaign,
          character_data: { ...state.campaign.character_data, ...updates },
        },
      };
    }),
  updateTurnNumber: (n) =>
    set((state) => {
      if (!state.campaign) return state;
      return { campaign: { ...state.campaign, turn_number: n } };
    }),
  setStreaming: (updates) => set((state) => ({ streaming: { ...state.streaming, ...updates } })),
  appendNarration: (chunk, stepIndex = 0) =>
    set((state) => ({
      streaming: {
        ...state.streaming,
        currentNarration: state.streaming.currentNarration + chunk,
        segments: upsertSegment(state.streaming.segments, stepIndex, (seg) => ({
          ...seg,
          text: seg.text + chunk,
        })),
      },
    })),
  appendSegmentDice: (dice, stepIndex) =>
    set((state) => ({
      streaming: {
        ...state.streaming,
        segments: upsertSegment(state.streaming.segments, stepIndex, (seg) => ({
          ...seg,
          dice: { ...(seg.dice || {}), ...dice },
        })),
      },
    })),
  appendSegmentNpc: (npc, stepIndex) =>
    set((state) => ({
      streaming: {
        ...state.streaming,
        segments: upsertSegment(state.streaming.segments, stepIndex, (seg) => ({
          ...seg,
          npc_dialogues: [...seg.npc_dialogues, npc],
        })),
      },
    })),
  setPendingDice: (dice) =>
    set((state) => ({
      streaming: { ...state.streaming, pendingDice: dice, diceRevealed: false },
    })),
  revealDice: () => {
    diceRevealCallback?.();
    set((state) => ({
      streaming: { ...state.streaming, diceRevealed: true, diceAwaitingReveal: false },
    }));
  },
  resetStreaming: () => set({ streaming: { ...initialStreaming } }),
  reset: () =>
    set({
      campaign: null,
      turnHistory: [],
      isProcessing: false,
      streaming: { ...initialStreaming },
    }),
}));
