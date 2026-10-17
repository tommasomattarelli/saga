import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import type { EditableWorld } from "../../../shared/api/client";

export function createWorldPayload(): EditableWorld {
  return {
    slug: "test-world",
    meta: { name: "Test World", author: "Author", version: "1.0", description: "", tags: [] },
    root: { kind: "world" },
    taxonomy: {
      kinds: [
        { name: "world", scale: "outdoor" },
        {
          name: "site",
          scale: "outdoor",
          params: [
            { name: "population", type: "int", min: 0, required: true },
            { name: "ratio", type: "float", max: 10 },
            { name: "motto", type: "str" },
            { name: "active", type: "bool" },
            { name: "custom" },
          ],
        },
        { name: "room", scale: "interior" },
      ],
      terrains: [{ name: "road", travel_multiplier: 1 }],
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
              { min: 0, label: "neutral" },
            ],
          },
        },
      },
      npc_fields: [{ name: "role", default: "traveler", scene: true }],
      npc_classes: [{ name: "guard", hp_class: "standard" }],
    },
    scenario: null,
    nodes: [
      {
        slug: "city",
        parent: null,
        kind: "site",
        name: "City",
        position: { x: 1, y: 2 },
        params: { population: 100, ratio: 1.5, motto: "Welcome" },
      },
      { slug: "room", parent: "city", kind: "room", name: "Room" },
      { slug: "hill", parent: null, kind: "site", name: "Hill" },
    ],
    edges: [{ slug: "road", from: "city", to: "hill", mode: "foot" }, { slug: "other" }],
    factions: [{ slug: "guild", name: "Guild" }, { slug: "other" }],
    npcs: [{ slug: "guide", name: "Guide", role: "guide" }, { slug: "other" }],
    encounters: [
      {
        slug: "events",
        dice: "1d6",
        entries: [{ roll: [1, 3], type: "event", description: "Rain" }],
      },
      { slug: "other" },
    ],
  };
}

export function renderWorldForm(
  form: (payload: EditableWorld, onChange: (payload: EditableWorld) => void) => ReactElement,
  initial = createWorldPayload(),
) {
  let current = initial;
  const update = (next: EditableWorld) => {
    current = next;
    view.rerender(form(current, update));
  };
  const view = render(form(current, update));
  return { ...view, getPayload: () => current };
}
