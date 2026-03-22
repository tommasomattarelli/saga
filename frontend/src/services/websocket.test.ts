import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GameWebSocket } from "./websocket";
import { useAuthStore } from "../stores/auth-store";

describe("GameWebSocket", () => {
  let mockWS: any;
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    useAuthStore.setState({ accessToken: "valid-token" });
    mockWS = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1, // Open
    };
    const MockWSClass = vi.fn(() => mockWS);
    (MockWSClass as any).OPEN = 1;
    globalThis.WebSocket = MockWSClass as any;
  });

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket;
  });

  it("should connect with token in URL", () => {
    const gws = new GameWebSocket("camp123");
    gws.connect();
    expect(globalThis.WebSocket).toHaveBeenCalledWith(expect.stringContaining("camp123"));
    expect(globalThis.WebSocket).toHaveBeenCalledWith(expect.stringContaining("token=valid-token"));
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
    const event = { data: JSON.stringify({ type: "test_event", data: "foo" }) };
    (globalThis.WebSocket as any).mock.results[0].value.onmessage(event);
    
    expect(handler).toHaveBeenCalledWith({ type: "test_event", data: "foo" });
  });

  it("should disconnect correctly", () => {
    const gws = new GameWebSocket("camp123");
    gws.connect();
    gws.disconnect();
    expect(mockWS.close).toHaveBeenCalled();
  });
});
