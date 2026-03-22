import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CharacterSheet from "./character-sheet";
import { useGameStore } from "../../stores/game-store";
import "@testing-library/jest-dom";

describe("CharacterSheet Component", () => {
  const mockChar = {
    name: "Grog",
    level: 5,
    xp: 2500,
    hp: 45,
    max_hp: 50,
    ac: 16,
    abilities: { strength: 18, dexterity: 12 },
    skills: { athletics: { level: 2, uses: 0, progress: 0 } },
    inventory: [{ name: "Axe", quantity: 1, type: "weapon" }],
    gold: 100,
  };

  it("should render character basic info", () => {
    useGameStore.setState({
      campaign: {
        character_data: mockChar,
      } as any,
    });

    render(<CharacterSheet />);

    expect(screen.getByText(/Grog/i)).toBeInTheDocument();
    expect(screen.getByText(/Level 5/i)).toBeInTheDocument();
    expect(screen.getByText("45/50")).toBeInTheDocument();
    expect(screen.getByText(/STR/i)).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("+4")).toBeInTheDocument(); // 18 -> +4
    expect(screen.getByText(/Athletics/i)).toBeInTheDocument();
    expect(screen.getByText(/Axe/i)).toBeInTheDocument();
  });

  it("should render empty inventory correctly", () => {
    const emptyChar = { ...mockChar, inventory: [], gold: 0 };
    useGameStore.setState({ campaign: { character_data: emptyChar } as any });
    render(<CharacterSheet />);
    expect(screen.getByText("Empty")).toBeInTheDocument();
    expect(screen.getByText("0 gold")).toBeInTheDocument();
  });

  it("should correctly handle negative ability modifiers", () => {
    useGameStore.setState({
      campaign: { character_data: { ...mockChar, abilities: { dexterity: 8 } } } as any,
    });
    render(<CharacterSheet />);
    expect(screen.getByText(/DEX/i)).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
  });

  it("should show empty state if no character data", () => {
    useGameStore.setState({ campaign: { character_data: null } as any });
    render(<CharacterSheet />);
    expect(screen.getByText("No character data")).toBeInTheDocument();
  });

  it("should show empty state if no campaign", () => {
    useGameStore.setState({ campaign: null });
    const { container } = render(<CharacterSheet />);
    expect(container.firstChild).toBeNull();
  });
});
