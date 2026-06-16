import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ActionInput from "../components/action-input";
import { useGameStore } from "../../../shared/stores/game-store";

beforeEach(() => {
  useGameStore.getState().reset();
});

describe("ActionInput", () => {
  it("renders the input and Seal button", () => {
    const onAction = vi.fn();
    render(<ActionInput onAction={onAction} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seal" })).toBeInTheDocument();
  });

  it("calls onAction and clears input on submit", () => {
    const onAction = vi.fn();
    render(<ActionInput onAction={onAction} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "I search the room" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Seal" }));

    expect(onAction).toHaveBeenCalledWith("I search the room");
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("does not submit empty input", () => {
    const onAction = vi.fn();
    render(<ActionInput onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: "Seal" }));
    expect(onAction).not.toHaveBeenCalled();
  });

  it("does not submit while loading", () => {
    const onAction = vi.fn();
    useGameStore.setState({ isLoading: true });
    render(<ActionInput onAction={onAction} />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "attack" },
    });
    fireEvent.click(screen.getByRole("button", { name: "…" }));

    expect(onAction).not.toHaveBeenCalled();
  });

  it("submits on Ctrl+Enter", () => {
    const onAction = vi.fn();
    render(<ActionInput onAction={onAction} />);

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "draw sword" } });
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });

    expect(onAction).toHaveBeenCalledWith("draw sword");
  });

  it("shows a character counter as the input nears the length cap", () => {
    const onAction = vi.fn();
    render(<ActionInput onAction={onAction} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "x".repeat(460) },
    });
    expect(screen.getByText("460/500")).toBeInTheDocument();
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
    render(<ActionInput onAction={onAction} />);
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onAction).toHaveBeenCalledWith("wait");
  });
});
