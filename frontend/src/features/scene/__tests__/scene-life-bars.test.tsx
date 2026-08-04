import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import SceneLifeBars, { npcsInScene } from "../components/scene-life-bars";
import type { WorldState } from "../../../shared/types";

const world = (overrides: Partial<WorldState> = {}): WorldState => ({
  meta: {
    schema_version: 8,
    world_name: "Test",
    current_season: "spring",
    current_location: "tavern",
  },
  npcs: {
    "1": { name: "Mirella", lifecycle: "alive", location: "tavern", hp: 18, max_hp: 22 },
    "2": { name: "Corvo", lifecycle: "alive", location: "docks", hp: 20, max_hp: 20 },
    "3": { name: "Bram", lifecycle: "dead", location: "tavern", hp: 0, max_hp: 8 },
  },
  ...overrides,
});

describe("npcsInScene", () => {
  it("keeps only the living characters standing here", () => {
    expect(npcsInScene(world()).map((n) => n.name)).toEqual(["Mirella"]);
  });

  it("is empty without a world state", () => {
    expect(npcsInScene(undefined)).toEqual([]);
  });
});

describe("SceneLifeBars", () => {
  it("shows a bar with no fight in sight (ADR 0003 B2)", () => {
    render(<SceneLifeBars worldState={world()} />);
    expect(screen.getByText("Mirella")).toBeInTheDocument();
    expect(screen.getByText("18/22")).toBeInTheDocument();
  });

  it("hides the dead and the absent", () => {
    render(<SceneLifeBars worldState={world()} />);
    expect(screen.queryByText("Bram")).not.toBeInTheDocument();
    expect(screen.queryByText("Corvo")).not.toBeInTheDocument();
  });

  it("renders nothing when the scene is empty", () => {
    const { container } = render(<SceneLifeBars worldState={world({ npcs: {} })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
