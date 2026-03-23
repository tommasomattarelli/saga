import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AxiosInstance } from "axios";
import api, { login, register, getMe, getCampaigns } from "./api";
import { useAuthStore } from "../stores/auth-store";

vi.mock("axios", async () => {
  const actual = await vi.importActual<typeof import("axios")>("axios");
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return {
    default: {
      ...actual.default,
      create: vi.fn(() => mockInstance),
    },
  };
});

describe("API Service", () => {
  const mockApi = vi.mocked(api as AxiosInstance);

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ accessToken: "test-token", refreshToken: "ref-token" });
  });

  it("should handle login request", async () => {
    vi.mocked(mockApi.post).mockResolvedValueOnce({ data: { access_token: "abc" } });
    const res = await login("user", "pass");
    expect(mockApi.post).toHaveBeenCalledWith("/auth/login", {
      username: "user",
      password: "pass",
    });
    expect(res.data.access_token).toBe("abc");
  });

  it("should handle register request", async () => {
    vi.mocked(mockApi.post).mockResolvedValueOnce({ data: { access_token: "reg" } });
    await register("user", "email@test.com", "pass");
    expect(mockApi.post).toHaveBeenCalledWith("/auth/register", {
      username: "user",
      email: "email@test.com",
      password: "pass",
    });
  });

  it("should handle getMe request", async () => {
    vi.mocked(mockApi.get).mockResolvedValueOnce({ data: { username: "me" } });
    await getMe();
    expect(mockApi.get).toHaveBeenCalledWith("/auth/me");
  });

  it("should handle getCampaigns request", async () => {
    vi.mocked(mockApi.get).mockResolvedValueOnce({ data: [] });
    await getCampaigns();
    expect(mockApi.get).toHaveBeenCalledWith("/campaigns");
  });
});
