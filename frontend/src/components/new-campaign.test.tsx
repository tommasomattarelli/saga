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
  const actual = await vi.importActual("react-router-dom") as any;
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
      </QueryClientProvider>
    );

  it("should render template picker in step 1", async () => {
    (getTemplates as any).mockResolvedValue({
      data: [
        { id: "t1", name: "Classic Fantasy", description: "Standard D&D", tags: ["fantasy"], difficulty: 1, author: "System" },
      ],
    });

    renderComponent();

    expect(screen.getByText("Choose your world")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Classic Fantasy")).toBeInTheDocument());
  });

  it("should move to step 2 when template is selected", async () => {
    (getTemplates as any).mockResolvedValue({
      data: [
        { id: "t1", name: "Classic Fantasy", description: "Standard D&D", tags: ["fantasy"], difficulty: 1, author: "System" },
      ],
    });

    renderComponent();
    
    const templateBtn = await screen.findByText("Classic Fantasy");
    fireEvent.click(templateBtn);

    expect(screen.getByText("Create your hero")).toBeInTheDocument();
  });
});
