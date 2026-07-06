import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import WorldMap from "../components/world-map";
import { getCampaignMap } from "../../../shared/api/client";
import type { MapData } from "../../../shared/api/client";
import { useUIStore } from "../../../shared/stores/ui-store";

vi.mock("../../../shared/api/client", () => ({
  getCampaignMap: vi.fn(),
}));

const MAP: MapData = {
  root: "world-1",
  player_position: "shrine-1",
  nodes: {
    "world-1": {
      name: "The Awakening",
      kind: "world",
      scale: "outdoor",
      position: { x: 0, y: 0 },
      parent: null,
      children: ["region-1"],
      has_status: false,
    },
    "region-1": {
      name: "The Verdant Reach",
      kind: "region",
      scale: "outdoor",
      position: { x: 10, y: 8 },
      parent: "world-1",
      children: ["shrine-1", "thorn-1"],
      has_status: false,
    },
    "shrine-1": {
      name: "Shrine of First Light",
      kind: "site",
      scale: "outdoor",
      position: { x: 2, y: 3 },
      parent: "region-1",
      children: [],
      has_status: false,
    },
    "thorn-1": {
      name: "Thornhaven",
      kind: "site",
      scale: "outdoor",
      position: { x: 4, y: 3 },
      parent: "region-1",
      children: [],
      has_status: false,
    },
  },
  edges: [{ from: "shrine-1", to: "thorn-1", mode: "foot" }],
};

const mockResponse = <T,>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config: {} as InternalAxiosRequestConfig,
});

describe("WorldMap", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ sidePanel: "map" });
  });

  const renderMap = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <WorldMap campaignId="c1" />
      </QueryClientProvider>,
    );

  it("renders pins for the level holding the player", async () => {
    vi.mocked(getCampaignMap).mockResolvedValue(mockResponse(MAP));
    renderMap();
    expect(await screen.findByText("Shrine of First Light")).toBeInTheDocument();
    expect(screen.getByText("Thornhaven")).toBeInTheDocument();
  });

  it("shows the breadcrumb up to the root and climbs on click", async () => {
    vi.mocked(getCampaignMap).mockResolvedValue(mockResponse(MAP));
    renderMap();
    const rootCrumb = await screen.findByRole("button", { name: "The Awakening" });
    fireEvent.click(rootCrumb);
    // At world level the only pinned child is the region
    expect(await screen.findByText("The Verdant Reach")).toBeInTheDocument();
  });

  it("does not render when the panel is closed", () => {
    useUIStore.setState({ sidePanel: null });
    vi.mocked(getCampaignMap).mockResolvedValue(mockResponse(MAP));
    renderMap();
    expect(screen.queryByText("Shrine of First Light")).not.toBeInTheDocument();
  });
});
