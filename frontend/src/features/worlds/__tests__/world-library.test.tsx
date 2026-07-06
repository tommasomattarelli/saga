import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import WorldLibrary from "../components/world-library";
import { getWorlds, createWorld } from "../../../shared/api/client";
import type { WorldOption } from "../../../shared/api/client";

vi.mock("../../../shared/api/client", () => ({
  getWorlds: vi.fn(),
  createWorld: vi.fn(),
  deleteWorld: vi.fn(),
  exportWorld: vi.fn(),
  importWorld: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockResponse = <T,>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config: {} as InternalAxiosRequestConfig,
});

const CARDS: WorldOption[] = [
  {
    slug: "the-awakening",
    name: "The Awakening",
    description: "Tutorial world",
    author: "SAGA Team",
    version: "1.0.0",
    tags: ["tutorial"],
  },
];

describe("WorldLibrary", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  beforeEach(() => vi.clearAllMocks());

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <WorldLibrary />
        </BrowserRouter>
      </QueryClientProvider>,
    );

  it("lists the worlds in the library", async () => {
    vi.mocked(getWorlds).mockResolvedValue(mockResponse(CARDS));
    renderPage();
    expect(await screen.findByText("The Awakening")).toBeInTheDocument();
    expect(screen.getByText("Tutorial world")).toBeInTheDocument();
  });

  it("creates a world and navigates to the editor", async () => {
    vi.mocked(getWorlds).mockResolvedValue(mockResponse(CARDS));
    vi.mocked(createWorld).mockResolvedValue(
      mockResponse({ ...CARDS[0], slug: "nuovo", name: "Nuovo" }),
    );
    renderPage();

    fireEvent.click(screen.getByText("New world"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Nuovo" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(createWorld).toHaveBeenCalledWith(expect.objectContaining({ name: "Nuovo" }));
      expect(mockNavigate).toHaveBeenCalledWith("/worlds/nuovo");
    });
  });

  it("opens the editor from a card", async () => {
    vi.mocked(getWorlds).mockResolvedValue(mockResponse(CARDS));
    renderPage();
    fireEvent.click(await screen.findByText("Edit"));
    expect(mockNavigate).toHaveBeenCalledWith("/worlds/the-awakening");
  });
});
