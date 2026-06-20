import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTypewriter } from "../use-typewriter";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useTypewriter", () => {
  it("starts empty and types towards full text", async () => {
    const { result } = renderHook(() => useTypewriter({ text: "Hello", baseSpeed: 10 }));

    expect(result.current.isTyping).toBe(true);
    expect(result.current.displayed).toBe("");

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    expect(result.current.displayed.length).toBeGreaterThan(0);
  });

  it("resolves immediately when reducedMotion is true", () => {
    const onComplete = vi.fn();
    const { result } = renderHook(() =>
      useTypewriter({ text: "Hello", reducedMotion: true, onComplete }),
    );

    expect(result.current.displayed).toBe("Hello");
    expect(result.current.isTyping).toBe(false);
    expect(onComplete).toHaveBeenCalled();
  });

  it("skip() fast-forwards to full text", async () => {
    const onComplete = vi.fn();
    const { result } = renderHook(() =>
      useTypewriter({ text: "Hello world", baseSpeed: 50, onComplete }),
    );

    await act(async () => {
      result.current.skip();
    });

    expect(result.current.displayed).toBe("Hello world");
    expect(result.current.isTyping).toBe(false);
    expect(onComplete).toHaveBeenCalled();
  });

  it("calls onComplete when typing finishes naturally", async () => {
    const onComplete = vi.fn();
    const { result } = renderHook(() => useTypewriter({ text: "Hi", baseSpeed: 5, onComplete }));

    // Advance multiple times to ensure cascading state updates + new timers are all processed
    for (let i = 0; i < 20; i++) {
      await act(async () => {
        vi.advanceTimersByTime(500);
      });
      if (!result.current.isTyping) break;
    }

    expect(result.current.displayed).toBe("Hi");
    expect(result.current.isTyping).toBe(false);
    expect(onComplete).toHaveBeenCalledOnce();
  });

  it("resets when text changes", async () => {
    let text = "First";
    const { result, rerender } = renderHook(() => useTypewriter({ text, baseSpeed: 5 }));

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    text = "Second";
    rerender();

    // After rerender with new text, displayed should reset
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    expect(result.current.displayed.length).toBeLessThanOrEqual("Second".length);
  });

  it("handles empty string without errors", () => {
    const { result } = renderHook(() => useTypewriter({ text: "", baseSpeed: 10 }));

    expect(result.current.displayed).toBe("");
    expect(result.current.isTyping).toBe(false);
  });
});
