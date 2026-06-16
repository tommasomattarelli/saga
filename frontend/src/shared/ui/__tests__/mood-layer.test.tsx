import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MoodLayer } from "../mood-layer";
import { useGameStore } from "../../stores/game-store";

describe("MoodLayer", () => {
  it("renders the fog svg for a fog mood", () => {
    useGameStore.setState({ currentMood: "dread_horror" });
    const { container } = render(<MoodLayer />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders no fog for a non-fog mood", () => {
    useGameStore.setState({ currentMood: "calm_exploration" });
    const { container } = render(<MoodLayer />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("always renders the gradient overlay", () => {
    useGameStore.setState({ currentMood: "combat_fury" });
    const { container } = render(<MoodLayer />);
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
