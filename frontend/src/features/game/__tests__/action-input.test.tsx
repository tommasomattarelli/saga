import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ActionInput from "../components/action-input";
import { useGameStore } from "../../../shared/stores/game-store";

beforeEach(() => {
  useGameStore.getState().reset();
});

describe("ActionInput", () => {
  it("renders the input and Act button", () => {
    const onAction = vi.fn();
    render(<ActionInput campaignId="c1" onAction={onAction} />);
    expect(screen.getByPlaceholderText("What do you do?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Act" })).toBeInTheDocument();
  });

  it("calls onAction and clears input on submit", () => {
    const onAction = vi.fn();
    render(<ActionInput campaignId="c1" onAction={onAction} />);

    fireEvent.change(screen.getByPlaceholderText("What do you do?"), {
      target: { value: "I search the room" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Act" }));

    expect(onAction).toHaveBeenCalledWith("I search the room");
    expect(screen.getByPlaceholderText("What do you do?")).toHaveValue("");
  });

  it("does not submit empty input", () => {
    const onAction = vi.fn();
    render(<ActionInput campaignId="c1" onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: "Act" }));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("does not submit while loading", () => {
    const onAction = vi.fn();
    useGameStore.setState({ isLoading: true });
    render(<ActionInput campaignId="c1" onAction={onAction} />);

    fireEvent.change(screen.getByPlaceholderText("What do you do?"), {
      target: { value: "attack" },
    });
    fireEvent.click(screen.getByRole("button", { name: "…" }));

    expect(onAction).not.toHaveBeenCalled();
  });

  it("submits on Ctrl+Enter", () => {
    const onAction = vi.fn();
    render(<ActionInput campaignId="c1" onAction={onAction} />);

    const input = screen.getByPlaceholderText("What do you do?");
    fireEvent.change(input, { target: { value: "draw sword" } });
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });

    expect(onAction).toHaveBeenCalledWith("draw sword");
  });

  it("shows suggested action pills and triggers them", () => {
    const onAction = vi.fn();
    useGameStore.setState({
      turnHistory: [
        {
          turn_number: 1,
          narration: "...",
          scene_mood: null,
          requires_player_action: true,
          suggested_actions: ["Look around", "Draw sword"],
        },
      ],
    });
    render(<ActionInput campaignId="c1" onAction={onAction} />);

    expect(screen.getByText("Look around")).toBeInTheDocument();
    expect(screen.getByText("Draw sword")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Look around"));
    expect(onAction).toHaveBeenCalledWith("Look around");
  });

  it("shows Continue button when last turn does not require player action", () => {
    const onAction = vi.fn();
    useGameStore.setState({
      turnHistory: [
        {
          turn_number: 1,
          narration: "...",
          scene_mood: null,
          requires_player_action: false,
        },
      ],
    });
    render(<ActionInput campaignId="c1" onAction={onAction} />);
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onAction).toHaveBeenCalledWith("wait");
  });
});
