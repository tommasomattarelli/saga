import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CompanionBar from "./companion-bar";
import { useGameStore } from "../../stores/game-store";
import { useUIStore } from "../../stores/ui-store";
import "@testing-library/jest-dom";

describe("CompanionBar Component", () => {
  it("should render companions when visible and data exists", () => {
    useUIStore.setState({ showCompanionBar: true });
    useGameStore.setState({
      campaign: {
        world_state: {
          companions: {
            c1: { name: "Bob", hp: 10, max_hp: 20, mood: "Happy", loyalty: 5 },
          },
        },
      } as any,
    });

    render(<CompanionBar />);

    expect(screen.getByText("Bob")).toBeInTheDocument();
    expect(screen.getByText("Happy")).toBeInTheDocument();
  });

  it("should return null if showCompanionBar is false", () => {
    useUIStore.setState({ showCompanionBar: false });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeNull();
  });

  it("should return null if no companions in world_state", () => {
    useUIStore.setState({ showCompanionBar: true });
    useGameStore.setState({
      campaign: {
        world_state: { companions: null },
      } as any,
    });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeNull();
  });
});
