import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSubmitAction } from "../use-submit-action";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";
import { useGameStore } from "../../../../shared/stores/game-store";

vi.mock("../../../../shared/api/client", () => ({
  submitAction: vi.fn(),
}));

const mockSubmitAction = vi.mocked(client.submitAction);

beforeEach(() => {
  vi.clearAllMocks();
  useGameStore.getState().reset();
});

const baseTurn = {
  turn_number: 2,
  narration: "The door creaks open.",
  scene_mood: "tense",
  player_action: "I open the door",
};

describe("useSubmitAction", () => {
  it("adds the turn to store on success", async () => {
    mockSubmitAction.mockResolvedValue({ data: baseTurn } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutation.mutateAsync("I open the door");
    });

    const turns = useGameStore.getState().turnHistory;
    expect(turns).toHaveLength(1);
    expect(turns[0].narration).toBe("The door creaks open.");
  });

  it("updates turn number on campaign in store", async () => {
    // Seed a campaign so updateTurnNumber has something to update
    useGameStore.setState({
      campaign: {
        id: "campaign-1",
        name: "Test",
        template_id: "t",
        status: "active",
        death_mode: "cronista",
        turn_number: 1,
        character_data: {} as never,
        world_state: {},
        quests: {},
        created_at: "",
        updated_at: "",
      },
    });

    mockSubmitAction.mockResolvedValue({ data: { ...baseTurn, turn_number: 5 } } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutation.mutateAsync("action");
    });

    expect(useGameStore.getState().campaign?.turn_number).toBe(5);
  });

  it("sets combat state when combat is active", async () => {
    const combatState = {
      active: true,
      round: 1,
      initiative_order: [],
      current_turn_index: 0,
    };

    mockSubmitAction.mockResolvedValue({
      data: { ...baseTurn, combat_state: combatState },
    } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutation.mutateAsync("attack");
    });

    expect(useGameStore.getState().combatState?.active).toBe(true);
  });

  it("clears combat state when combat ends", async () => {
    useGameStore.setState({
      combatState: { active: true, round: 2, initiative_order: [], current_turn_index: 0 },
    });

    mockSubmitAction.mockResolvedValue({
      data: { ...baseTurn, combat_state: { active: false, round: 0, initiative_order: [], current_turn_index: 0 } },
    } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutation.mutateAsync("flee");
    });

    expect(useGameStore.getState().combatState).toBeNull();
  });

  it("clears loading state on error", async () => {
    mockSubmitAction.mockRejectedValue(new Error("Backend down"));

    const { result } = renderHook(() => useSubmitAction("campaign-1"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      try {
        await result.current.mutation.mutateAsync("action");
      } catch {
        // expected
      }
    });

    expect(useGameStore.getState().isLoading).toBe(false);
  });
});
