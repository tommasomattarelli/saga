import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import DiceRoller from "../components/dice-roller";
import { useUIStore } from "../../../shared/stores/ui-store";
import type { DiceRollResult } from "../../../shared/types";

const makeRoll = (overrides: Partial<DiceRollResult> = {}): DiceRollResult => ({
  expression: "1d20+2",
  rolls: [15],
  modifier: 2,
  total: 17,
  difficulty: "normal",
  difficulty_draw: 0,
  success: true,
  outcome: "full_success",
  is_critical: false,
  ...overrides,
});

beforeEach(() => {
  useUIStore.setState({ soundEnabled: false });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DiceRoller — alwaysRevealed=true (historical turns)", () => {
  it("shows the roll result immediately without clicking", () => {
    render(<DiceRoller rolls={{ "STR save": makeRoll({ total: 17 }) }} alwaysRevealed />);
    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
  });

  it("shows the difficulty level instead of a target number", () => {
    render(
      <DiceRoller rolls={{ "STR save": makeRoll({ difficulty: "very_hard" }) }} alwaysRevealed />,
    );
    expect(screen.getByText("Very hard")).toBeInTheDocument();
  });

  it("shows Failure label on failed roll", () => {
    render(
      <DiceRoller
        rolls={{ "DEX save": makeRoll({ success: false, outcome: "hard_failure" }) }}
        alwaysRevealed
      />,
    );
    expect(screen.getByText("Failure")).toBeInTheDocument();
  });

  it("shows Critical success label on critical success", () => {
    render(
      <DiceRoller
        rolls={{ ATK: makeRoll({ success: true, outcome: "critical_success", is_critical: true }) }}
        alwaysRevealed
      />,
    );
    expect(screen.getByText("Critical success")).toBeInTheDocument();
  });

  it("shows Critical fail label on critical failure", () => {
    render(
      <DiceRoller
        rolls={{ ATK: makeRoll({ success: false, outcome: "critical_failure" }) }}
        alwaysRevealed
      />,
    );
    expect(screen.getByText("Critical fail")).toBeInTheDocument();
  });

  it("renders multiple dice", () => {
    render(
      <DiceRoller
        rolls={{
          "STR save": makeRoll(),
          "DEX save": makeRoll({ total: 5, success: false, outcome: "soft_failure" }),
        }}
        alwaysRevealed
      />,
    );
    expect(screen.getByText("STR save")).toBeInTheDocument();
    expect(screen.getByText("DEX save")).toBeInTheDocument();
  });
});

describe("DiceRoller — interactive (live turn)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows Roll button before clicking", () => {
    render(<DiceRoller rolls={{ "STR save": makeRoll() }} />);
    expect(screen.getByText("Roll")).toBeInTheDocument();
  });

  it("shows the difficulty level on the Roll button", () => {
    render(<DiceRoller rolls={{ "STR save": makeRoll({ difficulty: "hard" }) }} />);
    expect(screen.getByText(/Hard/)).toBeInTheDocument();
  });

  it("reveals result after animation completes", async () => {
    render(<DiceRoller rolls={{ "STR save": makeRoll({ total: 17 }) }} />);

    fireEvent.click(screen.getByText("Roll"));

    await vi.runAllTimersAsync();

    expect(screen.getByText("17")).toBeInTheDocument();
    expect(screen.getByText("Success")).toBeInTheDocument();
  });
});
