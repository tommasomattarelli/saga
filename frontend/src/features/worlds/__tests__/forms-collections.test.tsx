import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CollectionForm } from "../components/forms-collections";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;
const collections = {
  edge: "edges",
  faction: "factions",
  npc: "npcs",
  encounter: "encounters",
} as const;
type Kind = keyof typeof collections;
const entities: [Kind, string][] = [
  ["edge", "road"],
  ["faction", "guild"],
  ["npc", "guide"],
  ["encounter", "events"],
];

function renderCollection(kind: Kind, slug: string, world = createWorldPayload()) {
  const onSelect = vi.fn();
  const view = renderWorldForm(
    (payload, onChange) => (
      <CollectionForm
        payload={payload}
        kind={kind}
        slug={slug}
        onChange={onChange}
        onSelect={onSelect}
      />
    ),
    world,
  );
  return { ...view, onSelect };
}

describe("World collections", () => {
  it.each(entities)("renders no form for a missing %s", (kind) => {
    expect(renderCollection(kind, "missing").container).toBeEmptyDOMElement();
  });

  it.each(entities)("renames only the selected %s and updates selection", (kind, slug) => {
    const view = renderCollection(kind, slug);
    fireEvent.change(screen.getByLabelText(labels.slug), { target: { value: "renamed" } });
    expect(view.getPayload()[collections[kind]].map((entity) => entity.slug)).toEqual([
      "renamed",
      "other",
    ]);
    expect(view.onSelect).toHaveBeenCalledWith({ type: kind, slug: "renamed" });
  });

  it.each(entities)("deletes only the selected %s and returns to metadata", (kind, slug) => {
    const view = renderCollection(kind, slug);
    fireEvent.click(screen.getByRole("button", { name: labels.delete_entity }));
    expect(view.getPayload()[collections[kind]]).toEqual([{ slug: "other" }]);
    expect(view.onSelect).toHaveBeenCalledWith({ type: "meta" });
  });

  it("edits faction descriptions and filters blank goal lines", () => {
    const view = renderCollection("faction", "guild");
    for (const [label, value] of [
      [labels.name, "Explorers"],
      [labels.description, "Map the frontier"],
      [labels.goals, "Find a route\n\nProtect travelers\n"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().factions[0]).toEqual({
      slug: "guild",
      name: "Explorers",
      description: "Map the frontier",
      goals: ["Find a route", "Protect travelers"],
    });
  });

  it("edits edge references and converts or clears optional numbers", () => {
    const world = createWorldPayload();
    world.taxonomy.travel_modes.push({ name: "horse", speed_kmh: 12 });
    const view = renderCollection("edge", "road", world);
    for (const [label, value] of [
      [labels.edge_from, "room"],
      [labels.edge_to, "city"],
      [labels.mode, "horse"],
      [labels.terrain, "road"],
      [labels.travel_time, "2.25"],
      [labels.encounter_table, "events"],
      [labels.encounter_chance, "0.3"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().edges[0]).toEqual({
      slug: "road",
      from: "room",
      to: "city",
      mode: "horse",
      terrain: "road",
      travel_time: 2.25,
      encounter_table: "events",
      encounter_chance: 0.3,
    });
    for (const label of [
      labels.terrain,
      labels.travel_time,
      labels.encounter_table,
      labels.encounter_chance,
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    }
    for (const field of ["terrain", "travel_time", "encounter_table", "encounter_chance"]) {
      expect(view.getPayload().edges[0][field]).toBeUndefined();
    }
  });
});

describe("NPC authored fields and statblocks", () => {
  it("edits the name while preserving unrelated NPCs", () => {
    const view = renderCollection("npc", "guide");
    fireEvent.change(screen.getByLabelText(labels.name), { target: { value: "Kira" } });
    expect(view.getPayload().npcs[0].name).toBe("Kira");
    expect(view.getPayload().npcs[1]).toEqual({ slug: "other" });
  });

  it.each([
    [labels.location, "location", "room"],
    [labels.faction, "faction", "guild"],
    [labels.npc_class, "npc_class", "guard"],
    [labels.npc_hp_class, "hp_class", "tough"],
    [labels.npc_defense, "defense", "hard"],
    [labels.npc_damage_class, "damage_class", "light"],
    ["role", "role", "scout"],
  ])("sets and clears optional %s", (label, field, value) => {
    const view = renderCollection("npc", "guide");
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
    expect(view.getPayload().npcs[0][field]).toBe(value);
    fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
    expect(view.getPayload().npcs[0][field]).toBeUndefined();
  });

  it("supports default declarations and clears empty psychology seed maps", () => {
    const world = createWorldPayload();
    world.taxonomy.npc_fields = null;
    world.taxonomy.npc_classes = null;
    world.taxonomy.psychology = null;
    world.npcs[0].psychology = { trust: 10, respect: 5 };
    const view = renderCollection("npc", "guide", world);
    fireEvent.change(screen.getByLabelText("appearance"), { target: { value: "Scarred" } });
    fireEvent.change(screen.getByLabelText(labels.npc_class), { target: { value: "commoner" } });
    fireEvent.change(screen.getByLabelText("trust"), { target: { value: "" } });
    expect(view.getPayload().npcs[0].psychology).toEqual({ respect: 5 });
    fireEvent.change(screen.getByLabelText("respect"), { target: { value: "" } });
    expect(view.getPayload().npcs[0].psychology).toBeUndefined();
    fireEvent.change(screen.getByLabelText("affection"), { target: { value: "12" } });
    expect(view.getPayload().npcs[0]).toMatchObject({
      appearance: "Scarred",
      npc_class: "commoner",
      psychology: { affection: 12 },
    });
  });
});

describe("Authored encounter tables", () => {
  it("edits default roll ranges, entry types and descriptions", () => {
    const world = createWorldPayload();
    world.encounters[0].entries = [{}, { roll: [4, 6], type: "event" }];
    const view = renderCollection("encounter", "events", world);
    fireEvent.change(screen.getByLabelText(labels.dice), { target: { value: "1d12" } });
    for (const [label, value] of [
      [labels.roll_min, "2"],
      [labels.roll_max, "5"],
      [labels.entry_type, "combat"],
      [labels.description, "Wolves"],
    ]) {
      fireEvent.change(screen.getAllByLabelText(label)[0], { target: { value } });
    }
    expect(view.getPayload().encounters[0]).toMatchObject({
      dice: "1d12",
      entries: [
        { roll: [2, 5], type: "combat", description: "Wolves" },
        { roll: [4, 6], type: "event" },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add}` }));
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().encounters[0].entries).toEqual([
      { roll: [4, 6], type: "event" },
      { roll: [1, 1], type: "event", description: "" },
    ]);
  });

  it("initializes an absent entries array", () => {
    const world = createWorldPayload();
    world.encounters[0].entries = undefined;
    const view = renderCollection("encounter", "events", world);
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add}` }));
    expect(view.getPayload().encounters[0].entries).toEqual([
      { roll: [1, 1], type: "event", description: "" },
    ]);
  });
});
