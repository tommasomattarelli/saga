import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CombatTracker from "../components/combat-tracker";
import type { CombatState } from "../../../shared/types";

const baseCombat: CombatState = {
  active: true,
  round: 2,
  initiative_order: [
    { name: "Hero", initiative: 18, hp: 28, max_hp: 40, type: "player" },
    { name: "Goblin", initiative: 12, hp: 8, max_hp: 10, type: "enemy" },
    { name: "Miriam", initiative: 15, hp: 20, max_hp: 20, type: "companion" },
  ],
  current_turn_index: 0,
};

describe("CombatTracker", () => {
  it("renders round number and all combatants", () => {
    render(<CombatTracker combatState={baseCombat} />);
    expect(screen.getByText(/COMBAT - Round 2/i)).toBeInTheDocument();
    expect(screen.getByText("Hero")).toBeInTheDocument();
    expect(screen.getByText("Goblin")).toBeInTheDocument();
    expect(screen.getByText("Miriam")).toBeInTheDocument();
  });

  it("returns null when combat is not active", () => {
    const { container } = render(
      <CombatTracker combatState={{ ...baseCombat, active: false }} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows HP values for each combatant", () => {
    render(<CombatTracker combatState={baseCombat} />);
    expect(screen.getByText("28/40")).toBeInTheDocument();
    expect(screen.getByText("8/10")).toBeInTheDocument();
  });

  it("shows initiative values", () => {
    render(<CombatTracker combatState={baseCombat} />);
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("handles a dead combatant (hp <= 0)", () => {
    const deadCombat: CombatState = {
      ...baseCombat,
      initiative_order: [
        { name: "Hero", initiative: 18, hp: 0, max_hp: 40, type: "player" },
      ],
    };
    render(<CombatTracker combatState={deadCombat} />);
    expect(screen.getByText("Hero")).toBeInTheDocument();
    expect(screen.getByText("0/40")).toBeInTheDocument();
  });

  it("renders an empty initiative order without crashing", () => {
    render(<CombatTracker combatState={{ ...baseCombat, initiative_order: [] }} />);
    expect(screen.getByText(/COMBAT - Round 2/i)).toBeInTheDocument();
  });
});
