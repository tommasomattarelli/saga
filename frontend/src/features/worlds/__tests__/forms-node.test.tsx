import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NodeForm } from "../components/forms-node";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;

function renderNode(slug = "city", initial = createWorldPayload()) {
  const onSelect = vi.fn();
  const view = renderWorldForm(
    (payload, onChange) => (
      <NodeForm payload={payload} slug={slug} onChange={onChange} onSelect={onSelect} />
    ),
    initial,
  );
  return { ...view, onSelect };
}

describe("Taxonomy-driven node editing", () => {
  it("renders nothing for a missing node", () => {
    expect(renderNode("missing").container).toBeEmptyDOMElement();
  });

  it("renames a node and reparents its children without touching siblings", () => {
    const view = renderNode();
    fireEvent.change(screen.getByLabelText(labels.slug), { target: { value: "capital" } });

    expect(view.getPayload().nodes.map(({ slug, parent }) => ({ slug, parent }))).toEqual([
      { slug: "capital", parent: null },
      { slug: "room", parent: "capital" },
      { slug: "hill", parent: null },
    ]);
    expect(view.onSelect).toHaveBeenCalledWith({ type: "node", slug: "capital" });
  });

  it("edits descriptions and parent references, including returning to the root", () => {
    const view = renderNode();
    fireEvent.change(screen.getByLabelText(labels.name), { target: { value: "Capital" } });
    fireEvent.change(screen.getByLabelText(labels.description), {
      target: { value: "A fortified city" },
    });
    fireEvent.change(screen.getByLabelText(labels.parent), { target: { value: "hill" } });
    expect(view.getPayload().nodes[0]).toMatchObject({
      name: "Capital",
      description: "A fortified city",
      parent: "hill",
    });
    fireEvent.change(screen.getByLabelText(labels.parent), { target: { value: "" } });
    expect(view.getPayload().nodes[0].parent).toBeNull();
  });

  it("edits outdoor coordinates and optional numeric settings without losing the other axis", () => {
    const view = renderNode();
    for (const [label, value] of [
      ["x", "3"],
      ["y", "4"],
      [labels.elevation, "120"],
      [labels.km_per_unit, "0.5"],
      [labels.terrain, "road"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().nodes[0]).toMatchObject({
      position: { x: 3, y: 4 },
      elevation_m: 120,
      km_per_unit: 0.5,
      terrain: "road",
    });
    for (const label of [labels.elevation, labels.km_per_unit, labels.terrain]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    }
    expect(view.getPayload().nodes[0].elevation_m).toBeUndefined();
    expect(view.getPayload().nodes[0].km_per_unit).toBeUndefined();
    expect(view.getPayload().nodes[0].terrain).toBeUndefined();
  });

  it.each(["x", "y"])("initializes a missing position when editing %s", (axis) => {
    const world = createWorldPayload();
    world.nodes[0].position = undefined;
    const view = renderNode("city", world);
    fireEvent.change(screen.getByLabelText(axis), { target: { value: "7" } });

    expect(view.getPayload().nodes[0].position).toEqual(
      axis === "x" ? { x: 7, y: 0 } : { x: 0, y: 7 },
    );
  });

  it("switches between interior and outdoor kinds with the appropriate position", () => {
    const view = renderNode();
    fireEvent.change(screen.getByLabelText(labels.kind), { target: { value: "room" } });
    expect(view.getPayload().nodes[0].position).toBeUndefined();
    expect(screen.queryByLabelText("x")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(labels.kind), { target: { value: "site" } });
    expect(view.getPayload().nodes[0].position).toEqual({ x: 0, y: 0 });
    fireEvent.change(screen.getByLabelText(labels.kind), { target: { value: "world" } });
    expect(view.getPayload().nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  it("converts taxonomy parameters to their declared types and removes cleared values", () => {
    const view = renderNode();
    for (const [label, value] of [
      ["population *", "250"],
      ["ratio", "2.75"],
      ["motto", "Explore"],
      ["custom", "authored value"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByLabelText("active"));
    expect(view.getPayload().nodes[0].params).toEqual({
      population: 250,
      ratio: 2.75,
      motto: "Explore",
      custom: "authored value",
      active: true,
    });
    fireEvent.click(screen.getByLabelText("active"));
    fireEvent.change(screen.getByLabelText("population *"), { target: { value: "" } });
    expect(view.getPayload().nodes[0].params).toEqual({
      ratio: 2.75,
      motto: "Explore",
      custom: "authored value",
      active: false,
    });
  });

  it("initializes an absent parameter map", () => {
    const world = createWorldPayload();
    world.nodes[0].params = undefined;
    const view = renderNode("city", world);
    fireEvent.change(screen.getByLabelText("motto"), { target: { value: "Welcome" } });
    expect(view.getPayload().nodes[0].params).toEqual({ motto: "Welcome" });
  });

  it("adds, edits and removes interior exits and clears the locked flag", () => {
    const view = renderNode("room");
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add}` }));
    expect(view.getPayload().nodes[1].exits).toEqual([{ to: "outside" }]);
    fireEvent.change(screen.getByLabelText(labels.exit_to), { target: { value: "city" } });
    fireEvent.click(screen.getByLabelText(labels.locked));
    expect(view.getPayload().nodes[1].exits).toEqual([{ to: "city", locked: true }]);
    fireEvent.click(screen.getByLabelText(labels.locked));
    expect(view.getPayload().nodes[1].exits?.[0].locked).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add}` }));
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().nodes[1].exits).toEqual([{ to: "outside" }]);
    fireEvent.click(screen.getByRole("button", { name: "✕" }));
    expect(view.getPayload().nodes[1].exits).toEqual([]);
  });

  it("deletes all descendants even when children appear before their parents", () => {
    const world = createWorldPayload();
    world.nodes.unshift({ slug: "closet", parent: "room", kind: "room", name: "Closet" });
    const view = renderNode("city", world);
    fireEvent.click(screen.getByRole("button", { name: labels.delete_entity }));

    expect(view.getPayload().nodes.map((node) => node.slug)).toEqual(["hill"]);
    expect(view.onSelect).toHaveBeenCalledWith({ type: "meta" });
  });

  it("handles a node whose kind is no longer in the taxonomy", () => {
    const world = createWorldPayload();
    world.nodes[0].kind = "retired-kind";
    const view = renderNode("city", world);
    expect(screen.queryByLabelText("x")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("population *")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(labels.name), { target: { value: "Old settlement" } });
    expect(view.getPayload().nodes[0].name).toBe("Old settlement");
  });
});
