import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import GameView from "../components/game-view";
import {
  getCampaign,
  getRuntimeConfig,
  retryCampaignMemory,
  submitAction,
} from "../../../shared/api/client";
import { useGameStore } from "../../../shared/stores/game-store";
import type { Campaign } from "../../../shared/types";

vi.mock("../../../shared/api/client", () => ({
  getCampaign: vi.fn(),
  getTurns: vi.fn().mockResolvedValue({ data: [] }),
  getRuntimeConfig: vi.fn().mockResolvedValue({ data: { action_client_timeout_seconds: 73 } }),
  retryCampaignMemory: vi.fn().mockResolvedValue({ data: {} }),
  submitAction: vi.fn(),
}));

const mockParams = { campaignId: "c123" };
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useParams: () => mockParams,
  };
});

describe("GameView Component", () => {
  let queryClient: QueryClient;

  const mockCampaign: Campaign = {
    id: "c123",
    world_slug: "w1",
    language: "en",
    name: "Epic Quest",
    status: "active",
    difficulty: "medium",
    turn_number: 1,
    character_data: {
      name: "Hero",
      level: 1,
      xp: 0,
      hp: { current: 10, max: 10 },
      ac: 10,
      abilities: {},
      skills: {},
      inventory: [],
      equipped: {},
      gold: 0,
      background: "",
      notes: "",
      reputation: {},
    },
    world_state: { location: "Mystic Cave" },
    quests: { active: [], completed: [], failed: [], abandoned: [] },
    created_at: "now",
    updated_at: "now",
    active_head_turn_id: null,
    context_epoch: 0,
    memory_policy_id: null,
  };

  const createMockResponse = <T,>(data: T): AxiosResponse<T> => ({
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: {} as InternalAxiosRequestConfig,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    useGameStore.setState({ campaign: null, turnHistory: [] });
    vi.mocked(getRuntimeConfig).mockResolvedValue({
      data: { action_client_timeout_seconds: 73 },
    } as never);
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <GameView />
        </BrowserRouter>
      </QueryClientProvider>,
    );

  it("should show loading state initially", () => {
    vi.mocked(getCampaign).mockReturnValue(new Promise(() => {}));
    renderComponent();
    expect(screen.getByText("Loading your campaign…")).toBeInTheDocument();
  });

  it("should render campaign name when loaded", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));

    renderComponent();

    await waitFor(
      () => {
        expect(screen.getByText("Epic Quest")).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
  });

  it("keeps action entry disabled when runtime timeout configuration cannot load", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));
    vi.mocked(getRuntimeConfig).mockRejectedValue(new Error("offline"));
    renderComponent();

    await waitFor(() => expect(screen.getByLabelText("What do you do?")).toBeDisabled());
  });

  it("uses a fresh request ID after a definitive interrupted response", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));
    vi.mocked(submitAction)
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 409, data: { detail: { code: "action_interrupted" } } },
      })
      .mockImplementationOnce(
        async (_campaignId, submission) =>
          createMockResponse({
            turn_number: 2,
            narration: "Done",
            scene_mood: null,
            request_id: submission.request_id,
            turn_id: "00000000-0000-4000-8000-000000000017",
            head_turn_id: "00000000-0000-4000-8000-000000000017",
            context_epoch: 0,
          }) as never,
      );
    renderComponent();
    const input = await screen.findByLabelText("What do you do?");
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { value: "I open the gate" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(2));

    const first = vi.mocked(submitAction).mock.calls[0][1];
    const second = vi.mocked(submitAction).mock.calls[1][1];
    expect(first.request_id).not.toBe(second.request_id);
  });

  it("retains the request ID after an ambiguous network failure", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));
    vi.mocked(submitAction)
      .mockRejectedValueOnce(new Error("network lost"))
      .mockImplementationOnce(
        async (_campaignId, submission) =>
          createMockResponse({
            turn_number: 2,
            narration: "Done",
            scene_mood: null,
            request_id: submission.request_id,
            turn_id: "00000000-0000-4000-8000-000000000018",
            head_turn_id: "00000000-0000-4000-8000-000000000018",
            context_epoch: 0,
          }) as never,
      );
    renderComponent();
    const input = await screen.findByLabelText("What do you do?");
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { value: "I wait" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(2));

    expect(vi.mocked(submitAction).mock.calls[0][1].request_id).toBe(
      vi.mocked(submitAction).mock.calls[1][1].request_id,
    );
  });

  it("retains the request ID across an explicit memory retry", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));
    vi.mocked(submitAction)
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 503, data: { detail: { code: "memory_retry_required" } } },
      })
      .mockImplementationOnce(
        async (_campaignId, submission) =>
          createMockResponse({
            turn_number: 2,
            narration: "Done",
            scene_mood: null,
            request_id: submission.request_id,
            turn_id: "00000000-0000-4000-8000-000000000019",
            head_turn_id: "00000000-0000-4000-8000-000000000019",
            context_epoch: 0,
          }) as never,
      );
    renderComponent();
    const input = await screen.findByLabelText("What do you do?");
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { value: "I ask the oracle" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByRole("button", { name: /retry memory, then resubmit/i });
    fireEvent.click(screen.getByRole("button", { name: /retry memory, then resubmit/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(2));

    expect(vi.mocked(retryCampaignMemory)).toHaveBeenCalledWith("c123", null, 0);
    expect(vi.mocked(submitAction).mock.calls[0][1].request_id).toBe(
      vi.mocked(submitAction).mock.calls[1][1].request_id,
    );
  });

  it("offers explicit memory retry after a credential/configuration block", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));
    vi.mocked(submitAction)
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: { status: 503, data: { detail: { code: "memory_configuration_required" } } },
      })
      .mockImplementationOnce(
        async (_campaignId, submission) =>
          createMockResponse({
            turn_number: 2,
            narration: "Done",
            scene_mood: null,
            request_id: submission.request_id,
            turn_id: "00000000-0000-4000-8000-000000000020",
            head_turn_id: "00000000-0000-4000-8000-000000000020",
            context_epoch: 0,
          }) as never,
      );
    renderComponent();
    const input = await screen.findByLabelText("What do you do?");
    await waitFor(() => expect(input).not.toBeDisabled());
    fireEvent.change(input, { target: { value: "I ask the oracle" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    fireEvent.click(await screen.findByRole("button", { name: /retry memory, then resubmit/i }));
    await waitFor(() => expect(vi.mocked(submitAction)).toHaveBeenCalledTimes(2));
    expect(vi.mocked(retryCampaignMemory)).toHaveBeenCalledWith("c123", null, 0);
    expect(vi.mocked(submitAction).mock.calls[0][1].request_id).toBe(
      vi.mocked(submitAction).mock.calls[1][1].request_id,
    );
  });
});
