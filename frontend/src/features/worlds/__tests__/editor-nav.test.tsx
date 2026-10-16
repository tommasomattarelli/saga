import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EditorNav } from "../components/editor-nav";
import type { Selection } from "../components/editor-nav";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;

function renderNav(world = createWorldPayload(), selection: Selection = { type: "meta" }) {
  const onSelect = vi.fn();
  const view = renderWorldForm(
    (payload, onChange) => (
      <EditorNav payload={payload} selection={selection} onSelect={onSelect} onChange={onChange} />
    ),
    world,
  );
  return { ...view, onSelect };
}

describe("World editor navigation", () => {
  it.each(["meta", "taxonomy", "scenario"] as const)("selects the %s section", (type) => {
    const view = renderNav();
    fireEvent.click(screen.getByRole("button", { name: labels[`section_${type}`] }));
    expect(view.onSelect).toHaveBeenCalledWith({ type });
  });

  it.each([
    ["node", "City", "city"],
    ["edge", "road", "road"],
    ["faction", "Guild", "guild"],
    ["npc", "Guide", "guide"],
    ["encounter", "events", "events"],
  ] as const)("selects and highlights a %s", (type, name, slug) => {
    const view = renderNav(createWorldPayload(), { type, slug });
    const button = screen.getByRole("button", { name });
    expect(button).toHaveStyle({ color: "var(--accent)" });
    fireEvent.click(button);
    expect(view.onSelect).toHaveBeenCalledWith({ type, slug });
  });

  it("renders descendants and accepts the world slug as a root parent", () => {
    const world = createWorldPayload();
    world.nodes[0].parent = world.slug;
    const view = renderNav(world);
    fireEvent.click(screen.getByRole("button", { name: "Room" }));
    expect(view.onSelect).toHaveBeenCalledWith({ type: "node", slug: "room" });
  });

  it.each(["outdoor", "interior"] as const)(
    "adds unique root nodes using the first %s kind",
    (scale) => {
      const world = createWorldPayload();
      world.nodes.push(
        { slug: "new-place-1", name: "First", kind: "site", parent: null },
        { slug: "new-place-2", name: "Second", kind: "site", parent: null },
      );
      world.taxonomy.kinds = [{ name: "custom-kind", scale }];
      const view = renderNav(world);
      fireEvent.click(
        screen.getByRole("button", { name: `${labels.add} ${labels.section_nodes}` }),
      );
      const node = view.getPayload().nodes.slice(-1)[0];
      expect(node).toMatchObject({
        slug: "new-place-3",
        kind: "custom-kind",
        parent: null,
        name: labels.new_place,
      });
      expect(node?.position).toEqual(scale === "outdoor" ? { x: 0, y: 0 } : undefined);
      expect(view.onSelect).toHaveBeenCalledWith({ type: "node", slug: "new-place-3" });
    },
  );

  it.each([
    ["edge", "edges"],
    ["faction", "factions"],
    ["npc", "npcs"],
    ["encounter", "encounters"],
  ] as const)("creates unique %s entries and selects them", (kind, key) => {
    const world = createWorldPayload();
    world[key].push({ slug: `new-${kind}-1` });
    const view = renderNav(world);
    fireEvent.click(
      screen.getByRole("button", { name: `${labels.add} ${labels[`section_${key}`]}` }),
    );

    const created = view.getPayload()[key].slice(-1)[0];
    expect(created?.slug).toBe(`new-${kind}-2`);
    expect(view.onSelect).toHaveBeenCalledWith({ type: kind, slug: `new-${kind}-2` });
    if (kind === "edge") {
      expect(created).toMatchObject({ from: "city", to: "room", mode: "foot" });
    } else if (kind === "encounter") {
      expect(created).toMatchObject({
        dice: "1d6",
        entries: [{ roll: [1, 6], type: "event", description: "…" }],
      });
    } else {
      expect(created?.name).toBe(kind === "npc" ? labels.new_npc : labels.new_faction);
    }
  });

  it.each([0, 1])("creates an edge safely with %i available nodes", (count) => {
    const world = createWorldPayload();
    world.nodes = world.nodes.slice(0, count);
    world.taxonomy.travel_modes = [];
    const view = renderNav(world);
    fireEvent.click(screen.getByRole("button", { name: `${labels.add} ${labels.section_edges}` }));
    expect(view.getPayload().edges.slice(-1)[0]).toMatchObject({
      from: count ? "city" : "",
      to: count ? "city" : "",
      mode: "",
    });
  });
});
