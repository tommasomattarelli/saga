import { create } from "zustand";
import type { Campaign, TurnResponse, WorldState, CharacterData, DiceRollResult, CombatState, DeathEvent } from "../types";

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

const __DEV__ =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

interface StreamingState {
  isStreaming: boolean;
  currentNarration: string;
  pendingDice: Record<string, DiceRollResult> | null;
  diceRevealed: boolean;
  currentMood: string;
  combatState: CombatState | null;
  deathEvent: DeathEvent | null;
}

interface GameState {
  campaign: Campaign | null;
  turnHistory: TurnResponse[];
  isProcessing: boolean;
  streaming: StreamingState;
  setCampaign: (campaign: Campaign) => void;
  addTurn: (turn: TurnResponse) => void;
  setProcessing: (processing: boolean) => void;
  updateWorldState: (updates: Partial<WorldState>) => void;
  updateCharacter: (updates: Partial<CharacterData>) => void;
  setStreaming: (updates: Partial<StreamingState>) => void;
  appendNarration: (chunk: string) => void;
  setPendingDice: (dice: Record<string, DiceRollResult>) => void;
  revealDice: () => void;
  resetStreaming: () => void;
  reset: () => void;
}

const initialStreaming: StreamingState = {
  isStreaming: false,
  currentNarration: "",
  pendingDice: null,
  diceRevealed: false,
  currentMood: "neutral",
  combatState: null,
  deathEvent: null,
};

export const useGameStore = create<GameState>()((set) => ({
  campaign: null,
  turnHistory: [],
  isProcessing: false,
  streaming: { ...initialStreaming },
  setCampaign: (campaign) => set({ campaign }),
  addTurn: (turn) => set((state) => ({ turnHistory: [...state.turnHistory, turn] })),
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
  setStreaming: (updates) => set((state) => ({ streaming: { ...state.streaming, ...updates } })),
  appendNarration: (chunk) =>
    set((state) => ({
      streaming: {
        ...state.streaming,
        currentNarration: state.streaming.currentNarration + chunk,
      },
    })),
  setPendingDice: (dice) =>
    set((state) => ({
      streaming: { ...state.streaming, pendingDice: dice, diceRevealed: false },
    })),
  revealDice: () =>
    set((state) => ({
      streaming: { ...state.streaming, diceRevealed: true },
    })),
  resetStreaming: () => set({ streaming: { ...initialStreaming } }),
  reset: () =>
    set({
      campaign: null,
      turnHistory: [],
      isProcessing: false,
      streaming: { ...initialStreaming },
    }),
}));
