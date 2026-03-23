import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import NewCampaign from "./new-campaign";
import { getTemplates, createCampaign } from "../services/api";
import type { TemplateOption } from "../services/api";
import type { Campaign } from "../types";

vi.mock("../services/api", () => ({
  getTemplates: vi.fn(),
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

  it("should render template picker in step 1", async () => {
    vi.mocked(getTemplates).mockResolvedValue(
      createMockResponse<TemplateOption[]>([
        {
          id: "t1",
          slug: "classic",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          difficulty: 1,
          author: "System",
        },
      ]),
    );

    renderComponent();

    expect(screen.getByText("Choose your world")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Classic Fantasy")).toBeInTheDocument());
  });

  it("should move to step 2 when template is selected", async () => {
    vi.mocked(getTemplates).mockResolvedValue(
      createMockResponse<TemplateOption[]>([
        {
          id: "t1",
          slug: "classic",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          difficulty: 1,
          author: "System",
        },
      ]),
    );

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    expect(screen.getByText("Create your hero")).toBeInTheDocument();
  });

  it("should go back from step 2 to step 1", async () => {
    vi.mocked(getTemplates).mockResolvedValue(
      createMockResponse<TemplateOption[]>([
        {
          id: "t1",
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          difficulty: 1,
          author: "System",
          tags: [],
        },
      ]),
    );
    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const backBtn = screen.getByText("Back");
    fireEvent.click(backBtn);

    expect(screen.getByText("Choose your world")).toBeInTheDocument();
  });

  it("should call createCampaign on submit", async () => {
    vi.mocked(getTemplates).mockResolvedValue(
      createMockResponse<TemplateOption[]>([
        {
          id: "t1",
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          difficulty: 1,
          author: "System",
          tags: [],
        },
      ]),
    );
    vi.mocked(createCampaign).mockResolvedValue(createMockResponse({ id: "c1" } as Campaign));

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const nameInput = screen.getByPlaceholderText(/Leave blank/i);
    fireEvent.change(nameInput, { target: { value: "Durin" } });

    const submitBtn = screen.getByText("Begin the Saga →");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createCampaign).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith("/game/c1");
    });
  });

  it("should show error on failure", async () => {
    vi.mocked(getTemplates).mockResolvedValue(
      createMockResponse<TemplateOption[]>([
        {
          id: "t1",
          slug: "classic",
          name: "Classic Fantasy",
          description: "",
          difficulty: 1,
          author: "System",
          tags: [],
        },
      ]),
    );
    vi.mocked(createCampaign).mockRejectedValue(new Error("API Error"));

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const submitBtn = screen.getByText("Begin the Saga →");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Failed to create campaign/i)).toBeInTheDocument();
    });
  });

  it("should navigate back to campaigns when clicking top back link", async () => {
    vi.mocked(getTemplates).mockResolvedValue(createMockResponse<TemplateOption[]>([]));
    renderComponent();
    fireEvent.click(screen.getByText("← Back"));
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });
});
