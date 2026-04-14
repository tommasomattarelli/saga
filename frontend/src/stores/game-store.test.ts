import { describe, it, expect, beforeEach, vi } from "vitest";
import { useGameStore } from "./game-store";
import type { Campaign, TurnResponse, WorldState } from "../types";

const mockCampaign: Campaign = {
  id: "c1",
  name: "Test Campaign",
  template_id: "t1",
  status: "active",
  death_mode: "cronista",
  turn_number: 1,
  character_data: {
    name: "Hero",
    level: 1,
    xp: 0,
    hp: 10,
    max_hp: 10,
    ac: 10,
    abilities: { str: 10 },
    skills: {},
    inventory: [],
    equipped: {},
    gold: 0,
    background: "none",
    notes: "",
    reputation: {},
    active_quests: [],
  },
  world_state: {
    location: "Start Town",
    companions: {},
    factions: {},
  },
  quests: {},
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
};

const mockTurn: TurnResponse = {
  turn_number: 1,
  narration: "Turn 1 narration",
  dice_rolls: null,
  scene_mood: "calm",
  model_used: "test-model",
  requires_player_action: true,
};

describe("Game Store", () => {
  const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

  beforeEach(() => {
    useGameStore.setState({
      campaign: { ...mockCampaign },
      turnHistory: [],
      isLoading: false,
    });
    warnSpy.mockClear();
  });

  it("should initialize correctly", () => {
    useGameStore.getState().reset();
    expect(useGameStore.getState().campaign).toBeNull();
    expect(useGameStore.getState().turnHistory).toEqual([]);
    expect(useGameStore.getState().isLoading).toBe(false);
  });

  it("should set campaign", () => {
    useGameStore.getState().reset();
    useGameStore.getState().setCampaign(mockCampaign);
    expect(useGameStore.getState().campaign).toEqual(mockCampaign);
  });

  it("should add turn to history", () => {
    useGameStore.getState().addTurn(mockTurn);
    expect(useGameStore.getState().turnHistory).toHaveLength(1);
    expect(useGameStore.getState().turnHistory[0]).toEqual(mockTurn);
  });

  it("should set loading status", () => {
    useGameStore.getState().setLoading(true);
    expect(useGameStore.getState().isLoading).toBe(true);
  });

  it("should update world state", () => {
    useGameStore.getState().updateWorldState({ location: "New Town", weather: "rain" });
    const camp = useGameStore.getState().campaign;
    expect(camp?.world_state.location).toBe("New Town");
    expect(camp?.world_state.weather).toBe("rain");
  });

  it("should warn on invalid world state keys in dev", () => {
    useGameStore.getState().updateWorldState({ sidePanel: "inventory" } as unknown as WorldState);
    expect(warnSpy).toHaveBeenCalledWith("[game-store] WorldState leakage:", ["sidePanel"]);
  });

  it("should update character data", () => {
    useGameStore.getState().updateCharacter({ hp: 5, gold: 100 });
    const camp = useGameStore.getState().campaign;
    expect(camp?.character_data.hp).toBe(5);
    expect(camp?.character_data.gold).toBe(100);
  });
});
