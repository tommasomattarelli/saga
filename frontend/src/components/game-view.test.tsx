import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import GameView from "./game-view";
import { getCampaign } from "../services/api";
import { useGameStore } from "../stores/game-store";
import type { Campaign } from "../types";

vi.mock("../services/api", () => ({
  getCampaign: vi.fn(),
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
    template_id: "t123",
    name: "Epic Quest",
    status: "active",
    death_mode: "destino",
    turn_number: 1,
    character_data: {
      name: "Hero",
      level: 1,
      xp: 0,
      hp: 10,
      max_hp: 10,
      ac: 10,
      abilities: {},
      skills: {},
      inventory: [],
      equipped: {},
      gold: 0,
      background: "",
      notes: "",
      reputation: {},
      active_quests: [],
    },
    world_state: { location: "Mystic Cave" },
    quests: { active: [] },
    created_at: "now",
    updated_at: "now",
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
    vi.mocked(getCampaign).mockReturnValue(new Promise(() => {})); // Never resolves
    renderComponent();
    expect(screen.getByText("Loading your adventure...")).toBeInTheDocument();
  });

  it("should render campaign info when loaded", async () => {
    vi.mocked(getCampaign).mockResolvedValue(createMockResponse(mockCampaign));

    renderComponent();

    await waitFor(
      () => {
        expect(screen.getByText("Epic Quest")).toBeInTheDocument();
        expect(screen.getByText(/Mystic Cave/)).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
  });
});
