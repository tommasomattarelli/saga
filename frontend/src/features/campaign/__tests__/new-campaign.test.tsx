import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import NewCampaign from "../components/new-campaign";
import { getWorlds, createCampaign } from "../../../shared/api/client";
import type { WorldOption } from "../../../shared/api/client";
import type { Campaign } from "../../../shared/types";

vi.mock("../../../shared/api/client", () => ({
  getWorlds: vi.fn(),
  createCampaign: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("NewCampaign Component", () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const createMockResponse = <T,>(data: T): AxiosResponse<T> => ({
    data,
    status: 200,
    statusText: "OK",
    headers: {},
    config: {} as InternalAxiosRequestConfig,
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <NewCampaign />
        </BrowserRouter>
      </QueryClientProvider>,
    );

  it("should render world picker in step 1", async () => {
    vi.mocked(getWorlds).mockResolvedValue(
      createMockResponse<WorldOption[]>([
        {
          slug: "classic",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          version: "1.0.0",
          author: "System",
        },
      ]),
    );

    renderComponent();

    expect(screen.getByText("Choose a world")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Classic Fantasy")).toBeInTheDocument());
  });

  it("should move to step 2 when world is selected", async () => {
    vi.mocked(getWorlds).mockResolvedValue(
      createMockResponse<WorldOption[]>([
        {
          slug: "classic",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          version: "1.0.0",
          author: "System",
        },
      ]),
    );

    renderComponent();

    const worldBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(worldBtn);

    expect(await screen.findByText("Your hero")).toBeInTheDocument();
  });

  it("should go back from step 2 to step 1", async () => {
    vi.mocked(getWorlds).mockResolvedValue(
      createMockResponse<WorldOption[]>([
        {
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          version: "1.0.0",
          author: "System",
          tags: [],
        },
      ]),
    );
    renderComponent();

    const worldBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(worldBtn);

    const backBtn = await screen.findByText(/Back/);
    fireEvent.click(backBtn);

    expect(await screen.findByText("Choose a world")).toBeInTheDocument();
  });

  it("should call createCampaign on submit", async () => {
    vi.mocked(getWorlds).mockResolvedValue(
      createMockResponse<WorldOption[]>([
        {
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          version: "1.0.0",
          author: "System",
          tags: [],
        },
      ]),
    );
    vi.mocked(createCampaign).mockResolvedValue(createMockResponse({ id: "c1" } as Campaign));

    renderComponent();

    const worldBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(worldBtn);

    const nameInput = await screen.findByPlaceholderText(/Leave blank/i);
    fireEvent.change(nameInput, { target: { value: "Durin" } });
    fireEvent.click(screen.getByText(/Continue/));

    const submitBtn = await screen.findByText("Create campaign");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createCampaign).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith("/game/c1");
    });
  });

  it("should show error on failure", async () => {
    vi.mocked(getWorlds).mockResolvedValue(
      createMockResponse<WorldOption[]>([
        {
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          version: "1.0.0",
          author: "System",
          tags: [],
        },
      ]),
    );
    vi.mocked(createCampaign).mockRejectedValue(new Error("API Error"));

    renderComponent();

    const worldBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(worldBtn);

    fireEvent.click(await screen.findByText(/Continue/));

    const submitBtn = await screen.findByText("Create campaign");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/couldn't create the campaign/i)).toBeInTheDocument();
    });
  });

  it("should navigate back to campaigns when clicking top back link", async () => {
    vi.mocked(getWorlds).mockResolvedValue(createMockResponse<WorldOption[]>([]));
    renderComponent();
    fireEvent.click(screen.getByText(/Campaigns/));
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });
});
