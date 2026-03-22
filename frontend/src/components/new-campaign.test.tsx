import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NewCampaign from "./new-campaign";
import { getTemplates } from "../services/api";

vi.mock("../services/api", () => ({
  getTemplates: vi.fn(),
  createCampaign: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = (await vi.importActual("react-router-dom")) as any;
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("NewCampaign Component", () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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
    (getTemplates as any).mockResolvedValue({
      data: [
        {
          id: "t1",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          difficulty: 1,
          author: "System",
        },
      ],
    });

    renderComponent();

    expect(screen.getByText("Choose your world")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Classic Fantasy")).toBeInTheDocument());
  });

  it("should move to step 2 when template is selected", async () => {
    (getTemplates as any).mockResolvedValue({
      data: [
        {
          id: "t1",
          name: "Classic Fantasy",
          description: "Standard D&D",
          tags: ["fantasy"],
          difficulty: 1,
          author: "System",
        },
      ],
    });

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    expect(screen.getByText("Create your hero")).toBeInTheDocument();
  });

  it("should go back from step 2 to step 1", async () => {
    (getTemplates as any).mockResolvedValue({
      data: [{ id: "t1", name: "Classic Fantasy", difficulty: 1, author: "System" }],
    });
    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const backBtn = screen.getByText("Back");
    fireEvent.click(backBtn);

    expect(screen.getByText("Choose your world")).toBeInTheDocument();
  });

  it("should call createCampaign on submit", async () => {
    const { createCampaign } = await import("../services/api");
    (getTemplates as any).mockResolvedValue({
      data: [{ id: "t1", name: "Classic Fantasy", difficulty: 1, author: "System" }],
    });
    (createCampaign as any).mockResolvedValue({ data: { id: "c1" } });

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const nameInput = screen.getByPlaceholderText(/Leave blank/i);
    fireEvent.change(nameInput, { target: { value: "Durin" } });

    const submitBtn = screen.getByText("Begin the Saga →");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createCampaign).toHaveBeenCalledWith({
        template_id: "t1",
        name: "Durin's Adventure",
        death_mode: "cronista",
        character_data: { name: "Durin" },
      });
      expect(mockNavigate).toHaveBeenCalledWith("/game/c1");
    });
  });

  it("should show error on failure", async () => {
    const { createCampaign } = await import("../services/api");
    (getTemplates as any).mockResolvedValue({
      data: [{ id: "t1", name: "Classic Fantasy", difficulty: 1, author: "System" }],
    });
    (createCampaign as any).mockRejectedValue(new Error("API Error"));

    renderComponent();

    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    const submitBtn = screen.getByText("Begin the Saga →");
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Failed to create campaign/i)).toBeInTheDocument();
    });
  });

  it("should navigate back to campaigns when clicking top back link", () => {
    (getTemplates as any).mockResolvedValue({ data: [] });
    renderComponent();
    fireEvent.click(screen.getByText("← Back"));
    expect(mockNavigate).toHaveBeenCalledWith("/campaigns");
  });
});
