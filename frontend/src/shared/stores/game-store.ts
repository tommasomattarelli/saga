import { create } from "zustand";
import type { Campaign, TurnResponse, WorldState, CharacterData, CombatState } from "../types";

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

interface GameState {
  campaign: Campaign | null;
  turnHistory: TurnResponse[];
  isLoading: boolean;
  pendingAction: string | null;
  currentMood: string;
  combatState: CombatState | null;
  freshTurnNumber: number | null; // turn_number of the turn just submitted in this session
  hasPendingDice: boolean; // true when latest turn has unclicked dice

  setCampaign: (campaign: Campaign) => void;
  setTurnHistory: (turns: TurnResponse[]) => void;
  addTurn: (turn: TurnResponse) => void;
  setLoading: (loading: boolean) => void;
  setPendingAction: (action: string | null) => void;
  setCurrentMood: (mood: string) => void;
  setCombatState: (state: CombatState | null) => void;
  clearPendingDice: () => void;
  updateWorldState: (updates: Partial<WorldState>) => void;
  updateCharacter: (updates: Partial<CharacterData>) => void;
  updateTurnNumber: (n: number) => void;
  reset: () => void;
}

export const useGameStore = create<GameState>()((set) => ({
  campaign: null,
  turnHistory: [],
  isLoading: false,
  pendingAction: null,
  currentMood: "neutral",
  combatState: null,
  freshTurnNumber: null,
  hasPendingDice: false,

  setCampaign: (campaign) => set({ campaign }),
  setTurnHistory: (turns) => set({ turnHistory: turns, freshTurnNumber: null }),
  addTurn: (turn) => {
    const hasDice =
      (turn.dice_results && turn.dice_results.length > 0) ||
      !!(turn.dice_rolls && Object.keys(turn.dice_rolls).length > 0);
    set((state) => ({
      turnHistory: [...state.turnHistory, turn],
      freshTurnNumber: turn.turn_number,
      hasPendingDice: hasDice,
    }));
  },
  setLoading: (loading) => set({ isLoading: loading }),
  setPendingAction: (action) => set({ pendingAction: action }),
  setCurrentMood: (mood) => set({ currentMood: mood }),
  setCombatState: (combatState) => set({ combatState }),
  clearPendingDice: () => set({ hasPendingDice: false }),

  updateWorldState: (updates) =>
    set((state) => {
      if (__DEV__) {
        const leaked = Object.keys(updates).filter((k) => !ALLOWED_WORLD_STATE_KEYS.has(k));
        if (leaked.length > 0) {
          console.warn("[game-store] WorldState leakage:", leaked);
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

  reset: () =>
    set({
      campaign: null,
      turnHistory: [],
      isLoading: false,
      pendingAction: null,
      currentMood: "neutral",
      combatState: null,
      freshTurnNumber: null,
      hasPendingDice: false,
    }),
}));
