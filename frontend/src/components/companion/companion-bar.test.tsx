import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import CompanionBar from "./companion-bar";
import { useGameStore } from "../../stores/game-store";
import { useUIStore } from "../../stores/ui-store";
import "@testing-library/jest-dom";

describe("CompanionBar Component", () => {
  beforeEach(() => {
    useUIStore.setState({ showCompanionBar: true });
    useGameStore.setState({ campaign: null });
  });

  it("should render companion info when present", () => {
    useGameStore.setState({
      campaign: {
        world_state: {
          companions: {
            elara_key: { name: "Elara", hp: 15, max_hp: 20, mood: "Happy", loyalty: 10 },
          },
        },
      } as any,
    });

    render(<CompanionBar />);
    expect(screen.getByText("Elara")).toBeInTheDocument();
    expect(screen.getByText("Happy")).toBeInTheDocument();
  });

  it("should render nothing if showCompanionBar is false", () => {
    useUIStore.setState({ showCompanionBar: false });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeNull();
  });

  it("should render an empty div if companions exists but is empty", () => {
    useGameStore.setState({
      campaign: {
        world_state: { companions: {} },
      } as any,
    });
    const { container } = render(<CompanionBar />);
    expect(container.firstChild).toBeInTheDocument();
    expect(container.firstChild?.childNodes).toHaveLength(0);
  });
});
