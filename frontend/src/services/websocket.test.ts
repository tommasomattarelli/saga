import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GameWebSocket } from "./websocket";
import { useAuthStore } from "../stores/auth-store";

describe("GameWebSocket", () => {
  let mockWS: { send: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn>; readyState: number; onmessage?: (e: { data: string }) => void };
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    useAuthStore.setState({ accessToken: "valid-token" });
    mockWS = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1, // Open
    };
    
    // We need to satisfy the WebSocket constructor signature
    const MockWSClass = vi.fn().mockImplementation(() => mockWS);
    (MockWSClass as unknown as { OPEN: number }).OPEN = 1;
    globalThis.WebSocket = MockWSClass as unknown as typeof WebSocket;
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
  });

  it("should connect with token in URL", () => {
    new GameWebSocket("camp123").connect();
    expect(globalThis.WebSocket).toHaveBeenCalledWith(expect.stringContaining("camp123"), undefined);
    expect(globalThis.WebSocket).toHaveBeenCalledWith(expect.stringContaining("token=valid-token"), undefined);
  });

  it("should send message if socket is open", () => {
    const gws = new GameWebSocket("camp123");
    gws.connect();
    gws.send({ type: "test", payload: "hello" });
    expect(mockWS.send).toHaveBeenCalledWith(JSON.stringify({ type: "test", payload: "hello" }));
  });

  it("should register and trigger handlers", () => {
    const gws = new GameWebSocket("camp123");
    const handler = vi.fn();
    gws.on("test_event", handler);

    gws.connect();
    
    // Simulate incoming message
    const wsInstance = vi.mocked(globalThis.WebSocket).mock.results[0].value as typeof mockWS;
    const event = { data: JSON.stringify({ type: "test_event", data: "foo" }) };
    if (wsInstance.onmessage) {
      wsInstance.onmessage(event);
    }

    expect(handler).toHaveBeenCalledWith({ type: "test_event", data: "foo" });
  });

  it("should disconnect correctly", () => {
    const gws = new GameWebSocket("camp123");
    gws.connect();
    gws.disconnect();
    expect(mockWS.close).toHaveBeenCalled();
  });
});
