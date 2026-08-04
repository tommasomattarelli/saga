import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSubmitAction } from "../use-submit-action";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";
import { useGameStore } from "../../../../shared/stores/game-store";

const nullScrollRef = { current: null } as { current: HTMLDivElement | null };

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

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
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
        world_slug: "w1",
        status: "active",
        difficulty: "easy",
        turn_number: 1,
        character_data: {} as never,
        world_state: {},
        quests: {},
        created_at: "",
        updated_at: "",
      },
    });

    mockSubmitAction.mockResolvedValue({ data: { ...baseTurn, turn_number: 5 } } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutation.mutateAsync("action");
    });

    expect(useGameStore.getState().campaign?.turn_number).toBe(5);
  });

  it("clears loading state on error", async () => {
    mockSubmitAction.mockRejectedValue(new Error("Backend down"));

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
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
