import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock axios and auth store before importing refreshMutex
const mockPost = vi.fn();
vi.mock("axios", () => ({ default: { post: mockPost } }));

const mockSetTokens = vi.fn();
vi.mock("../../../shared/stores/auth-store", () => ({
  useAuthStore: { getState: () => ({ setTokens: mockSetTokens }) },
}));

describe("refreshMutex", () => {
  beforeEach(() => {
    vi.resetModules();
    mockPost.mockReset();
    mockSetTokens.mockReset();
  });

  it("calls refresh once for two concurrent 401s", async () => {
    mockPost.mockResolvedValue({
      data: { access_token: "new-token", refresh_token: "rt", token_type: "bearer" },
    });

    const { refreshMutex } = await import("../refresh-mutex");

    const [a, b] = await Promise.all([refreshMutex("rt"), refreshMutex("rt")]);

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(a).toBe("new-token");
    expect(b).toBe("new-token");
  });

  it("resets inflight after completion so next call fires fresh", async () => {
    mockPost.mockResolvedValue({
      data: { access_token: "tok-1", refresh_token: "rt", token_type: "bearer" },
    });
    const { refreshMutex } = await import("../refresh-mutex");
    await refreshMutex("rt");

    mockPost.mockResolvedValue({
      data: { access_token: "tok-2", refresh_token: "rt", token_type: "bearer" },
    });
    const result = await refreshMutex("rt");
    expect(result).toBe("tok-2");
    expect(mockPost).toHaveBeenCalledTimes(2);
  });
});
