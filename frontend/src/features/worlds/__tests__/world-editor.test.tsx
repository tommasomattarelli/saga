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
    psychology: {
      first_impression_multiplier: 3,
      max_delta_per_turn: 10,
      axes: {
        trust: {
          range: [-100, 100],
          default: 0,
          bands: [
            { min: -100, label: "wary" },
            { min: -10, label: "neutral" },
          ],
        },
        honor: {
          range: [-50, 50],
          default: 0,
          bands: [{ min: -50, label: "shamed" }],
        },
      },
    },
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
  npcs: [{ slug: "kira", name: "Kira", role: "guard" }],
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

  it("renders the world's psychology axes in the taxonomy form", async () => {
    vi.mocked(getWorld).mockResolvedValue(mockResponse(WORLD));
    renderEditor();

    fireEvent.click(await screen.findByText("Taxonomy"));
    expect(await screen.findByDisplayValue("trust")).toBeInTheDocument();
    expect(screen.getByDisplayValue("honor")).toBeInTheDocument();
    expect(screen.getByDisplayValue("wary")).toBeInTheDocument();
    expect(screen.getByLabelText("First impression multiplier")).toHaveValue(3);
  });

  it("edits an NPC psychology seed against the world axes", async () => {
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

    fireEvent.click(await screen.findByText("Kira"));
    // axis inputs come from the world's own psychology taxonomy
    fireEvent.change(await screen.findByLabelText("honor"), { target: { value: "-20" } });
    fireEvent.click(screen.getByText("Save world"));

    await waitFor(() => {
      const sent = vi.mocked(saveWorld).mock.calls[0][1];
      expect(sent.npcs[0].psychology).toEqual({ honor: -20 });
    });
  });

  it("renders world npc_fields in the taxonomy form and the NPC form", async () => {
    // ADR 0009 G1/G3: declared fields drive both the taxonomy section and the NPC form.
    const world = {
      ...WORLD,
      taxonomy: {
        ...WORLD.taxonomy,
        npc_fields: [{ name: "role", default: "Commoner", scene: true }, { name: "honor_code" }],
      },
      npcs: [{ slug: "kira", name: "Kira", role: "guard", honor_code: "strict" }],
    };
    vi.mocked(getWorld).mockResolvedValue(mockResponse(world));
    renderEditor();

    fireEvent.click(await screen.findByText("Taxonomy"));
    expect(await screen.findByDisplayValue("honor_code")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Commoner")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Kira"));
    expect(await screen.findByLabelText("honor_code")).toHaveValue("strict");
    expect(screen.getByLabelText("role")).toHaveValue("guard");
  });

  it("removing an npc_field prunes authored values behind a confirm (G5)", async () => {
    const world = {
      ...WORLD,
      taxonomy: {
        ...WORLD.taxonomy,
        npc_fields: [{ name: "role", scene: true }, { name: "honor_code" }],
      },
      npcs: [{ slug: "kira", name: "Kira", honor_code: "strict" }],
    };
    vi.mocked(getWorld).mockResolvedValue(mockResponse(world));
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
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderEditor();

    fireEvent.click(await screen.findByText("Taxonomy"));
    await screen.findByDisplayValue("honor_code");
    // remove buttons of the npc_fields rows are the last ✕ pair; click honor_code's
    const row = screen.getByDisplayValue("honor_code").closest("div")!.parentElement!;
    fireEvent.click(row.querySelector("button")!);
    expect(confirmSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByText("Save world"));
    await waitFor(() => {
      const sent = vi.mocked(saveWorld).mock.calls[0][1];
      expect(sent.taxonomy.npc_fields).toEqual([{ name: "role", scene: true }]);
      expect(sent.npcs[0]).not.toHaveProperty("honor_code");
    });
    confirmSpy.mockRestore();
  });

  it("removing a psychology axis prunes NPC seeds behind a confirm (G5)", async () => {
    const world = {
      ...WORLD,
      npcs: [{ slug: "kira", name: "Kira", psychology: { honor: -20 } }],
    };
    vi.mocked(getWorld).mockResolvedValue(mockResponse(world));
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
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderEditor();

    fireEvent.click(await screen.findByText("Taxonomy"));
    const honorInput = await screen.findByDisplayValue("honor");
    const axisRow = honorInput.closest("div")!.parentElement!;
    const removeBtn = [...axisRow.querySelectorAll("button")].find((b) => b.textContent === "✕")!;
    fireEvent.click(removeBtn);
    expect(confirmSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByText("Save world"));
    await waitFor(() => {
      const sent = vi.mocked(saveWorld).mock.calls[0][1];
      expect(Object.keys(sent.taxonomy.psychology!.axes)).toEqual(["trust"]);
      expect(sent.npcs[0].psychology).toBeUndefined();
    });
    confirmSpy.mockRestore();
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
