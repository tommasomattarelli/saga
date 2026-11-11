import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useSubmitAction } from "../use-submit-action";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";
import { useGameStore } from "../../../../shared/stores/game-store";

const nullScrollRef = { current: null } as { current: HTMLDivElement | null };

vi.mock("../../../../shared/api/client", () => ({
  submitAction: vi.fn(),
  getRuntimeConfig: vi.fn().mockResolvedValue({ data: { action_client_timeout_seconds: 73 } }),
}));

const mockSubmitAction = vi.mocked(client.submitAction);

beforeEach(() => {
  vi.clearAllMocks();
  useGameStore.getState().reset();
  useGameStore.setState({
    campaign: {
      id: "campaign-1",
      name: "Test",
      world_slug: "w1",
      language: "en",
      status: "active",
      difficulty: "easy",
      turn_number: 1,
      character_data: {} as never,
      world_state: {},
      quests: { active: [], completed: [], failed: [], abandoned: [] },
      created_at: "",
      updated_at: "",
      active_head_turn_id: null,
      context_epoch: 0,
      memory_policy_id: null,
    },
  });
});

const baseTurn = {
  request_id: "00000000-0000-4000-8000-000000000007",
  turn_id: "00000000-0000-4000-8000-000000000014",
  head_turn_id: "00000000-0000-4000-8000-000000000014",
  context_epoch: 0,
  turn_number: 2,
  narration: "The door creaks open.",
  scene_mood: "tense",
  player_action: "I open the door",
};

describe("useSubmitAction", () => {
  it("adds the turn to store on success", async () => {
    mockSubmitAction.mockResolvedValue({
      data: { ...baseTurn, request_id: "00000000-0000-4000-8000-000000000001" },
    } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await act(async () => {
      await result.current.mutation.mutateAsync({
        action: "I open the door",
        requestId: "00000000-0000-4000-8000-000000000001",
      });
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
        language: "en",
        status: "active",
        difficulty: "easy",
        turn_number: 1,
        character_data: {} as never,
        world_state: {},
        quests: { active: [], completed: [], failed: [], abandoned: [] },
        created_at: "",
        updated_at: "",
        active_head_turn_id: null,
        context_epoch: 0,
        memory_policy_id: null,
      },
    });

    mockSubmitAction.mockResolvedValue({
      data: {
        ...baseTurn,
        request_id: "00000000-0000-4000-8000-000000000002",
        turn_number: 5,
      },
    } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await act(async () => {
      await result.current.mutation.mutateAsync({
        action: "action",
        requestId: "00000000-0000-4000-8000-000000000002",
      });
    });

    expect(useGameStore.getState().campaign?.turn_number).toBe(5);
  });

  it("replaces the quest registry from the turn response", async () => {
    useGameStore.setState({
      campaign: {
        id: "campaign-1",
        name: "Test",
        world_slug: "w1",
        language: "en",
        status: "active",
        difficulty: "easy",
        turn_number: 1,
        character_data: {} as never,
        world_state: {},
        quests: { active: [], completed: [], failed: [], abandoned: [] },
        created_at: "",
        updated_at: "",
        active_head_turn_id: null,
        context_epoch: 0,
        memory_policy_id: null,
      },
    });

    mockSubmitAction.mockResolvedValue({
      data: {
        ...baseTurn,
        request_id: "00000000-0000-4000-8000-000000000003",
        quests: {
          active: [
            { id: "dragon_hunt", name: "Dragon Hunt", description: "Slay it", objectives: [] },
          ],
          completed: [],
          failed: [],
          abandoned: [],
        },
      },
    } as never);

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await act(async () => {
      await result.current.mutation.mutateAsync({
        action: "action",
        requestId: "00000000-0000-4000-8000-000000000003",
      });
    });

    expect(useGameStore.getState().campaign?.quests.active.map((q) => q.id)).toEqual([
      "dragon_hunt",
    ]);
  });

  it("clears loading state on error", async () => {
    mockSubmitAction.mockRejectedValue(new Error("Backend down"));

    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await act(async () => {
      try {
        await result.current.mutation.mutateAsync({
          action: "action",
          requestId: "00000000-0000-4000-8000-000000000004",
        });
      } catch {
        // expected
      }
    });

    expect(useGameStore.getState().isLoading).toBe(false);
  });

  it("does not apply a late success after the store changed campaigns", async () => {
    let resolveAction: ((value: { data: typeof baseTurn }) => void) | undefined;
    mockSubmitAction.mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve as (value: { data: typeof baseTurn }) => void;
      }) as never,
    );
    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    let submission: Promise<unknown>;
    act(() => {
      submission = result.current.submit("action", "00000000-0000-4000-8000-000000000005");
    });
    await waitFor(() => expect(mockSubmitAction).toHaveBeenCalledTimes(1));
    useGameStore.setState({ campaign: { ...useGameStore.getState().campaign!, id: "campaign-2" } });
    await act(async () => {
      resolveAction?.({
        data: { ...baseTurn, request_id: "00000000-0000-4000-8000-000000000005" },
      });
      await submission!;
    });

    expect(useGameStore.getState().campaign?.id).toBe("campaign-2");
    expect(useGameStore.getState().turnHistory).toEqual([]);
  });

  it("ignores a replay of a turn already applied to the current campaign", async () => {
    const response = {
      ...baseTurn,
      request_id: "00000000-0000-4000-8000-000000000006",
      turn_id: "00000000-0000-4000-8000-000000000011",
      head_turn_id: "00000000-0000-4000-8000-000000000011",
      context_epoch: 0,
    };
    mockSubmitAction.mockResolvedValue({ data: response } as never);
    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await act(async () => {
      await result.current.submit("action", "00000000-0000-4000-8000-000000000006");
    });
    const campaignAfterFirstApply = useGameStore.getState().campaign;
    await act(async () => {
      await result.current.submit("action", "00000000-0000-4000-8000-000000000006");
    });

    expect(useGameStore.getState().turnHistory).toHaveLength(1);
    expect(useGameStore.getState().campaign).toEqual(campaignAfterFirstApply);
  });

  it("rejects an action response whose request identity does not match before applying it", async () => {
    mockSubmitAction.mockResolvedValue({
      data: {
        ...baseTurn,
        request_id: "00000000-0000-4000-8000-000000000099",
        turn_id: "00000000-0000-4000-8000-000000000012",
        head_turn_id: "00000000-0000-4000-8000-000000000012",
        context_epoch: 0,
      },
    } as never);
    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.actionReady).toBe(true));

    await expect(
      result.current.submit("action", "00000000-0000-4000-8000-000000000013"),
    ).rejects.toThrow();

    expect(useGameStore.getState().turnHistory).toEqual([]);
    expect(useGameStore.getState().campaign?.turn_number).toBe(1);
  });

  it("keeps actions unavailable when runtime timeout config is invalid", async () => {
    vi.mocked(client.getRuntimeConfig).mockResolvedValueOnce({
      data: { action_client_timeout_seconds: 0 },
    } as never);
    const { result } = renderHook(() => useSubmitAction("campaign-1", nullScrollRef), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.actionReady).toBe(false));
    expect(mockSubmitAction).not.toHaveBeenCalled();
  });
});
