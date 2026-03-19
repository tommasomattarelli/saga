import { create } from "zustand";
import type { Campaign, TurnResponse, WorldState, CharacterData } from "../types";

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
