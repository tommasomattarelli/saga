import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import GameView from "./game-view";
import { getCampaign } from "../services/api";
import { useGameStore } from "../stores/game-store";

vi.mock("../services/api", () => ({
  getCampaign: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom") as any;
  return {
    ...actual,
    useParams: () => ({ campaignId: "c123" }),
  };
});

describe("GameView Component", () => {
  let queryClient: QueryClient;

  const mockCampaign = {
    id: "c123",
    name: "Epic Quest",
    turn_number: 1,
    world_state: { location: "Mystic Cave" },
    character_data: { name: "Hero" },
    quests: { active: [] }
  };

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
      </QueryClientProvider>
    );

  it("should show loading state initially", () => {
    (getCampaign as any).mockReturnValue(new Promise(() => {})); // Never resolves
    renderComponent();
    expect(screen.getByText("Loading your adventure...")).toBeInTheDocument();
  });

  it("should render campaign info when loaded", async () => {
    (getCampaign as any).mockResolvedValue({ data: mockCampaign });
    
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Epic Quest")).toBeInTheDocument();
      expect(screen.getByText(/Mystic Cave/)).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
