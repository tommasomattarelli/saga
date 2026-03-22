import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CampaignSelect from "./campaign-select";
import { getCampaigns } from "../services/api";

vi.mock("../services/api", () => ({
  getCampaigns: vi.fn(),
}));

describe("CampaignSelect Component", () => {
  const queryClient = new QueryClient();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render list of campaigns", async () => {
    (getCampaigns as any).mockResolvedValue({
      data: [
        { id: "1", name: "The Dragon Raid", status: "active", turn_number: 5, updated_at: "2024-01-01" },
      ],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CampaignSelect />
        </BrowserRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText("Your Sagas")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("The Dragon Raid")).toBeInTheDocument());
    expect(screen.getByText("Turn 5")).toBeInTheDocument();
  });

  it("should show empty state if no campaigns", async () => {
    (getCampaigns as any).mockResolvedValue({ data: [] });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <CampaignSelect />
        </BrowserRouter>
      </QueryClientProvider>
    );

    await waitFor(() => expect(screen.getByText("No campaigns yet. Start a new adventure!")).toBeInTheDocument());
  });
});
