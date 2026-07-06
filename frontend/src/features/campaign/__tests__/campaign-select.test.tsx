import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import CampaignSelect from "../components/campaign-select";
import { getCampaigns } from "../../../shared/api/client";
import type { Campaign } from "../../../shared/types";

vi.mock("../../../shared/api/client", () => ({
  getCampaigns: vi.fn(),
  deleteCampaign: vi.fn(),
}));

describe("CampaignSelect Component", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockResponse = <T,>(data: T): AxiosResponse<T> => ({
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: {} as InternalAxiosRequestConfig,
  });

  const mockCampaigns: Campaign[] = [
    {
      id: "1",
      template_id: "t1",
      name: "The Dragon Raid",
      status: "active",
      death_mode: "ironman",
      turn_number: 5,
      character_data: {
        name: "Test",
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
        active_quests: [],
      },
      world_state: {},
      quests: {},
      created_at: "2024-01-01",
      updated_at: "2024-01-01",
    },
  ];

  it("should render list of campaigns", async () => {
    vi.mocked(getCampaigns).mockResolvedValue(mockResponse<Campaign[]>(mockCampaigns));

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CampaignSelect />
        </BrowserRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("SAGA")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Open The Dragon Raid")).toBeInTheDocument());
  });

  it("should show empty state if no campaigns", async () => {
    vi.mocked(getCampaigns).mockResolvedValue(mockResponse<Campaign[]>([]));

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CampaignSelect />
        </BrowserRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText("New campaign")).toBeInTheDocument());
  });
});
