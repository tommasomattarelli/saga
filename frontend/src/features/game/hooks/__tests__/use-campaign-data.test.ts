import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useCampaignData } from "../use-campaign-data";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";
import { useGameStore } from "../../../../shared/stores/game-store";

vi.mock("../../../../shared/api/client", () => ({
  getCampaign: vi.fn(),
  getTurns: vi.fn(),
}));

const mockGetCampaign = vi.mocked(client.getCampaign);
const mockGetTurns = vi.mocked(client.getTurns);

const mockCampaign = {
  id: "c1",
  name: "The Lost Realm",
  world_slug: "w1",
  status: "active",
  difficulty: "easy",
  turn_number: 3,
  character_data: {
    name: "Tomma",
    level: 2,
    xp: 300,
    hp: { current: 20, max: 28 },
    ac: 14,
    abilities: {},
    skills: {},
    inventory: [],
    equipped: {},
    gold: 50,
    background: "",
    notes: "",
    reputation: {},
    active_quests: [],
  },
  world_state: {},
  quests: {},
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

beforeEach(() => {
  vi.clearAllMocks();
  useGameStore.getState().reset();
  mockGetCampaign.mockResolvedValue({ data: mockCampaign } as never);
  mockGetTurns.mockResolvedValue({ data: [] } as never);
});

describe("useCampaignData", () => {
  it("sets campaign in store on load", async () => {
    renderHook(() => useCampaignData("c1"), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(useGameStore.getState().campaign?.id).toBe("c1");
    });
  });

  it("populates turn history in reversed order", async () => {
    const turns = [
      { turn_number: 1, narration: "First", scene_mood: null, player_action: "go" },
      { turn_number: 2, narration: "Second", scene_mood: null, player_action: "look" },
    ];
    mockGetTurns.mockResolvedValue({ data: turns } as never);

    renderHook(() => useCampaignData("c1"), { wrapper: createWrapper() });

    await waitFor(() => {
      const history = useGameStore.getState().turnHistory;
      expect(history).toHaveLength(2);
      // getTurns returns desc from server; hook reverses to asc for display
      expect(history[0].turn_number).toBe(2);
    });
  });

  it("does not query when campaignId is undefined", () => {
    renderHook(() => useCampaignData(undefined), { wrapper: createWrapper() });

    expect(mockGetCampaign).not.toHaveBeenCalled();
    expect(mockGetTurns).not.toHaveBeenCalled();
  });

  it("sets combat state from world_state if active", async () => {
    const combatState = {
      active: true,
      round: 1,
      initiative_order: [],
      current_turn_index: 0,
    };
    mockGetCampaign.mockResolvedValue({
      data: { ...mockCampaign, world_state: { combat_state: combatState } },
    } as never);

    renderHook(() => useCampaignData("c1"), { wrapper: createWrapper() });

    await waitFor(() => {
      expect(useGameStore.getState().combatState?.active).toBe(true);
    });
  });

  it("returns loading true while fetching", () => {
    mockGetCampaign.mockReturnValue(new Promise(() => {}));
    mockGetTurns.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useCampaignData("c1"), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });
});
