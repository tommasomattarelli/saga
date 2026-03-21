import { create } from "zustand";
import type { Campaign, TurnResponse, WorldState, CharacterData } from "../types";

// Narrative world state keys that are authoritative on the backend.
// This mirrors backend/app/memory/world_state.py ALLOWED_WORLD_STATE_KEYS.
// UI-only state (sidePanel, soundEnabled, theme, etc.) must NEVER appear here —
// keep those in ui-store.ts so they stay in memory and never reach the DB.
const ALLOWED_WORLD_STATE_KEYS = new Set([
  "meta", "locations", "factions", "npcs", "companions",
  "time_of_day", "weather", "global_flags",
]);

/** True in development builds — stripped by the bundler in production. */
const __DEV__ = typeof window !== "undefined"
  && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");


interface GameState {
  campaign: Campaign | null;
  turnHistory: TurnResponse[];
  isProcessing: boolean;
  setCampaign: (campaign: Campaign) => void;
  addTurn: (turn: TurnResponse) => void;
  setProcessing: (processing: boolean) => void;
  updateWorldState: (updates: Partial<WorldState>) => void;
  updateCharacter: (updates: Partial<CharacterData>) => void;
  reset: () => void;
}

export const useGameStore = create<GameState>()((set) => ({
  campaign: null,
  turnHistory: [],
  isProcessing: false,
  setCampaign: (campaign) => set({ campaign }),
  addTurn: (turn) =>
    set((state) => ({ turnHistory: [...state.turnHistory, turn] })),
  setProcessing: (processing) => set({ isProcessing: processing }),
  updateWorldState: (updates) =>
    set((state) => {
      if (__DEV__) {
        const leaked = Object.keys(updates).filter(
          (k) => !ALLOWED_WORLD_STATE_KEYS.has(k),
        );
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
  reset: () => set({ campaign: null, turnHistory: [], isProcessing: false }),
}));
