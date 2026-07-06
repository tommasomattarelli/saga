import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";
import WorldEditor from "../components/world-editor";
import { getWorld, saveWorld } from "../../../shared/api/client";
import type { EditableWorld } from "../../../shared/api/client";

vi.mock("../../../shared/api/client", () => ({
  getWorld: vi.fn(),
  saveWorld: vi.fn(),
}));

const mockResponse = <T,>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config: {} as InternalAxiosRequestConfig,
});

const WORLD: EditableWorld = {
  slug: "test-world",
  meta: { name: "Test World", author: "t", version: "1.0.0", description: "", tags: [] },
  root: { kind: "world", description: "" },
  taxonomy: {
    kinds: [
      { name: "world", scale: "outdoor" },
      {
        name: "site",
        scale: "outdoor",
        params: [{ name: "population", type: "int", required: false, min: 0 }],
      },
      { name: "room", scale: "interior" },
    ],
    terrains: [{ name: "road", travel_multiplier: 0.75 }],
    travel_modes: [{ name: "foot", speed_kmh: 4 }],
  },
  scenario: null,
  nodes: [
    {
      slug: "karak",
      parent: "test-world",
      kind: "site",
      name: "Karak",
      position: { x: 1, y: 2 },
      params: { population: 400 },
    },
  ],
  edges: [],
  factions: [],
  npcs: [],
  encounters: [],
};

describe("WorldEditor", () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  beforeEach(() => vi.clearAllMocks());

  const renderEditor = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/worlds/test-world"]}>
          <Routes>
            <Route path="/worlds/:slug" element={<WorldEditor />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it("renders the nav tree and opens a taxonomy-driven node form", async () => {
    vi.mocked(getWorld).mockResolvedValue(mockResponse(WORLD));
    renderEditor();

    fireEvent.click(await screen.findByText("Karak"));
    // param field from the world's own taxonomy (P0)
    expect(await screen.findByLabelText("population")).toHaveValue(400);
  });

  it("edits a field and saves the world", async () => {
    vi.mocked(getWorld).mockResolvedValue(mockResponse(WORLD));
    vi.mocked(saveWorld).mockResolvedValue(
      mockResponse({
        slug: "test-world",
        name: "Test World",
        description: "",
        author: "t",
        version: "1.0.0",
        tags: [],
      }),
    );
    renderEditor();

    fireEvent.click(await screen.findByText("Karak"));
    fireEvent.change(await screen.findByLabelText("population"), { target: { value: "999" } });
    fireEvent.click(screen.getByText("Save world"));

    await waitFor(() => {
      expect(saveWorld).toHaveBeenCalled();
      const sent = vi.mocked(saveWorld).mock.calls[0][1];
      expect(sent.nodes[0].params?.population).toBe(999);
    });
  });

  it("shows validation errors from a rejected save", async () => {
    vi.mocked(getWorld).mockResolvedValue(mockResponse(WORLD));
    vi.mocked(saveWorld).mockRejectedValue({
      response: {
        data: { detail: { message: "World 'test-world' is invalid", errors: ["karak: bad"] } },
      },
    });
    renderEditor();

    fireEvent.click(await screen.findByText("Karak"));
    fireEvent.change(await screen.findByLabelText("population"), { target: { value: "1" } });
    fireEvent.click(screen.getByText("Save world"));

    expect(await screen.findByText("karak: bad")).toBeInTheDocument();
  });
});
