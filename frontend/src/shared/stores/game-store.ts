import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type { Campaign, TurnResponse, WorldState, CharacterData, QuestRegistry } from "../types";

interface GameState {
  campaign: Campaign | null;
  turnHistory: TurnResponse[];
  isLoading: boolean;
  pendingAction: string | null;
  freshTurnNumber: number | null; // turn_number of the turn just submitted in this session
  hasPendingDice: boolean; // true when latest turn has unclicked dice

  setCampaign: (campaign: Campaign) => void;
  setTurnHistory: (turns: TurnResponse[]) => void;
  addTurn: (turn: TurnResponse) => void;
  applyTurn: (turn: TurnResponse) => void;
  setLoading: (loading: boolean) => void;
  setPendingAction: (action: string | null) => void;
  clearPendingDice: () => void;
  updateWorldState: (updates: Partial<WorldState>) => void;
  updateCharacter: (updates: Partial<CharacterData>) => void;
  updateQuests: (quests: QuestRegistry) => void;
  updateTurnNumber: (n: number) => void;
  reset: () => void;
}

export const useGameStore = create<GameState>()(
  devtools(
    (set) => ({
      campaign: null,
      turnHistory: [],
      isLoading: false,
      pendingAction: null,
      freshTurnNumber: null,
      hasPendingDice: false,

      setCampaign: (campaign) => set({ campaign }),
      setTurnHistory: (turns) => set({ turnHistory: turns, freshTurnNumber: null }),
      addTurn: (turn) => {
        const hasDice =
          (turn.dice_results && turn.dice_results.length > 0) ||
          !!(turn.dice_rolls && Object.keys(turn.dice_rolls).length > 0);
        set((state) => ({
          turnHistory:
            turn.turn_id && state.turnHistory.some((item) => item.turn_id === turn.turn_id)
              ? state.turnHistory
              : [...state.turnHistory, turn],
          freshTurnNumber: turn.turn_number,
          hasPendingDice: hasDice,
        }));
      },
      applyTurn: (turn) =>
        set((state) => {
          if (turn.turn_id && state.turnHistory.some((item) => item.turn_id === turn.turn_id))
            return state;
          const campaign = state.campaign;
          if (!campaign) return state;
          const hasDice =
            (turn.dice_results && turn.dice_results.length > 0) ||
            !!(turn.dice_rolls && Object.keys(turn.dice_rolls).length > 0);
          return {
            turnHistory: [...state.turnHistory, turn],
            freshTurnNumber: turn.turn_number,
            hasPendingDice: hasDice,
            campaign: {
              ...campaign,
              ...(turn.head_turn_id ? { active_head_turn_id: turn.head_turn_id } : {}),
              ...(turn.context_epoch !== undefined ? { context_epoch: turn.context_epoch } : {}),
              ...(turn.world_state ? { world_state: turn.world_state } : {}),
              ...(turn.character_data ? { character_data: turn.character_data } : {}),
              ...(turn.quests ? { quests: turn.quests } : {}),
              turn_number: turn.turn_number || campaign.turn_number,
            },
          };
        }),
      setLoading: (loading) => set({ isLoading: loading }),
      setPendingAction: (action) => set({ pendingAction: action }),
      clearPendingDice: () => set({ hasPendingDice: false }),

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

      updateQuests: (quests) =>
        set((state) => {
          if (!state.campaign) return state;
          return { campaign: { ...state.campaign, quests } };
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
          freshTurnNumber: null,
          hasPendingDice: false,
        }),
    }),
    { name: "game-store", enabled: import.meta.env.DEV },
  ),
);
