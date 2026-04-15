import { describe, it, expect, beforeEach } from "vitest";
import { useGameStore } from "../game-store";
import type { Campaign, TurnResponse } from "../../types";

const makeCampaign = (overrides: Partial<Campaign> = {}): Campaign => ({
  id: "c1",
  name: "Test Saga",
  template_id: "t1",
  status: "active",
  death_mode: "cronista",
  turn_number: 1,
  character_data: { name: "Hero", level: 1, xp: 0, hp: { current: 20, max: 20 }, ac: 10, abilities: {}, skills: {}, inventory: [], equipped: {}, gold: 0, background: "", notes: "", reputation: {}, active_quests: [] },
  world_state: {},
  quests: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  ...overrides,
});

const makeTurn = (n: number): TurnResponse => ({
  turn_number: n,
  narration: `Turn ${n}`,
  scene_mood: "neutral",
});

describe("game-store", () => {
  beforeEach(() => {
    useGameStore.getState().reset();
  });

  it("setCampaign sets campaign", () => {
    const c = makeCampaign();
    useGameStore.getState().setCampaign(c);
    expect(useGameStore.getState().campaign?.id).toBe("c1");
  });

  it("addTurn appends and sets freshTurnNumber", () => {
    useGameStore.getState().setCampaign(makeCampaign());
    const t = makeTurn(1);
    useGameStore.getState().addTurn(t);
    const state = useGameStore.getState();
    expect(state.turnHistory).toHaveLength(1);
    expect(state.freshTurnNumber).toBe(1);
  });

  it("setTurnHistory resets freshTurnNumber", () => {
    useGameStore.getState().setCampaign(makeCampaign());
    useGameStore.getState().addTurn(makeTurn(1));
    useGameStore.getState().setTurnHistory([makeTurn(2)]);
    expect(useGameStore.getState().freshTurnNumber).toBeNull();
  });

  it("updateWorldState merges into campaign.world_state", () => {
    useGameStore.getState().setCampaign(makeCampaign({ world_state: { location: "town" } }));
    useGameStore.getState().updateWorldState({ weather: "rain" });
    const ws = useGameStore.getState().campaign?.world_state;
    expect(ws?.location).toBe("town");
    expect(ws?.weather).toBe("rain");
  });

  it("setCombatState and clear", () => {
    useGameStore.getState().setCombatState({ active: true, round: 1, initiative_order: [], current_turn_index: 0 });
    expect(useGameStore.getState().combatState?.active).toBe(true);
    useGameStore.getState().setCombatState(null);
    expect(useGameStore.getState().combatState).toBeNull();
  });

  it("reset clears all state", () => {
    useGameStore.getState().setCampaign(makeCampaign());
    useGameStore.getState().addTurn(makeTurn(1));
    useGameStore.getState().reset();
    const s = useGameStore.getState();
    expect(s.campaign).toBeNull();
    expect(s.turnHistory).toHaveLength(0);
    expect(s.isLoading).toBe(false);
  });
});
