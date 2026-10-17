import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetaForm, ScenarioForm, TaxonomyForm } from "../components/forms-world";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;

describe("World metadata and scenario forms", () => {
  it("updates metadata, normalizes tags and preserves root attributes", () => {
    const view = renderWorldForm((payload, onChange) => (
      <MetaForm payload={payload} onChange={onChange} />
    ));
    for (const [label, value] of [
      [labels.name, "New World"],
      [labels.author, "New Author"],
      [labels.version, "2.0"],
      [labels.description, "A living world"],
      [labels.tags, " fantasy, , mystery , "],
      [labels.root_description, "The continent"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().meta).toEqual({
      name: "New World",
      author: "New Author",
      version: "2.0",
      description: "A living world",
      tags: ["fantasy", "mystery"],
    });
    expect(view.getPayload().root).toEqual({ kind: "world", description: "The continent" });
  });

  it("creates and edits an opening without losing quest or story-arc data", () => {
    const world = createWorldPayload();
    world.scenario = {
      opening: { narration: "", start_location: "", time_of_day: "", weather: "" },
      initial_quests: [{ name: "Find the guide" }],
      story_arcs: [{ name: "The lost city" }],
    };
    const view = renderWorldForm(
      (payload, onChange) => <ScenarioForm payload={payload} onChange={onChange} />,
      world,
    );
    for (const [label, value] of [
      [labels.opening_narration, "A bell rings"],
      [labels.start_location, "city"],
      [labels.time_of_day, "dawn"],
      [labels.weather, "rain"],
      [labels.dm_persona, "Patient and observant"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().scenario).toEqual({
      opening: {
        narration: "A bell rings",
        start_location: "city",
        time_of_day: "dawn",
        weather: "rain",
      },
      initial_quests: [{ name: "Find the guide" }],
      story_arcs: [{ name: "The lost city" }],
      dm_persona: "Patient and observant",
    });
  });

  it("initializes the scenario when none was authored", () => {
    const view = renderWorldForm((payload, onChange) => (
      <ScenarioForm payload={payload} onChange={onChange} />
    ));
    fireEvent.change(screen.getByLabelText(labels.opening_narration), {
      target: { value: "A new beginning" },
    });
    expect(view.getPayload().scenario).toMatchObject({
      opening: { narration: "A new beginning" },
      initial_quests: [],
      story_arcs: [],
    });
  });
});

describe("Taxonomy collections", () => {
  it("edits, adds and removes kinds while keeping at least one", () => {
    const view = renderWorldForm((payload, onChange) => (
      <TaxonomyForm payload={payload} onChange={onChange} />
    ));
    fireEvent.change(screen.getAllByLabelText(labels.kind_name)[1], {
      target: { value: "settlement" },
    });
    fireEvent.change(screen.getAllByLabelText(labels.kind_scale)[1], {
      target: { value: "interior" },
    });
    expect(view.getPayload().taxonomy.kinds[1]).toMatchObject({
      name: "settlement",
      scale: "interior",
    });
    const section = screen.getAllByLabelText(labels.kind_name)[0].closest("section")!;
    fireEvent.click(within(section).getByRole("button", { name: `+ ${labels.add}` }));
    expect(view.getPayload().taxonomy.kinds).toHaveLength(4);
    for (let index = 0; index < 3; index++) {
      fireEvent.click(within(section).getAllByRole("button", { name: "✕" })[0]);
    }
    expect(view.getPayload().taxonomy.kinds).toHaveLength(1);
    expect(within(section).getByRole("button", { name: "✕" })).toBeDisabled();
  });

  it("edits numeric terrain and travel settings and allows empty collections", () => {
    const view = renderWorldForm((payload, onChange) => (
      <TaxonomyForm payload={payload} onChange={onChange} />
    ));
    for (const [label, value] of [
      [labels.terrain_name, "mud"],
      [labels.terrain_multiplier, "1.75"],
      [labels.mode_name, "horse"],
      [labels.mode_speed, "12.5"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    expect(view.getPayload().taxonomy.terrains).toEqual([{ name: "mud", travel_multiplier: 1.75 }]);
    expect(view.getPayload().taxonomy.travel_modes).toEqual([{ name: "horse", speed_kmh: 12.5 }]);
    for (const label of [labels.terrain_name, labels.mode_name]) {
      const section = screen.getByLabelText(label).closest("section")!;
      fireEvent.click(within(section).getByRole("button", { name: `+ ${labels.add}` }));
      fireEvent.click(within(section).getAllByRole("button", { name: "✕" })[0]);
      fireEvent.click(within(section).getByRole("button", { name: "✕" }));
    }
    expect(view.getPayload().taxonomy.terrains).toEqual([]);
    expect(view.getPayload().taxonomy.travel_modes).toEqual([]);
  });
});
