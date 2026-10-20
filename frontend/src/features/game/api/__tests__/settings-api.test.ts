import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AxiosInstance } from "axios";
import api from "../../../../shared/api/client";
import {
  cancelEmbeddingIndex,
  classifySettingsError,
  getEmbeddingIndexStatus,
  getSettings,
  patchSettings,
  putApiKeys,
  putServerKeyConsents,
  retryEmbeddingIndex,
} from "../../api/settings-api";

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

const mockApi = vi.mocked(api as AxiosInstance);

describe("settings api", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reads the settings of the signed-in user", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { preferred_language: "en" } } as never);

    const response = await getSettings();

    expect(mockApi.get).toHaveBeenCalledWith("/settings");
    expect(response.data.preferred_language).toBe("en");
  });

  it("patches a profile", async () => {
    mockApi.patch.mockResolvedValueOnce({ data: {} } as never);

    await patchSettings({ generation_provider: null, generation_model: null });

    expect(mockApi.patch).toHaveBeenCalledWith("/settings", {
      generation_provider: null,
      generation_model: null,
    });
  });

  it("writes API keys without returning the raw response", async () => {
    mockApi.put.mockResolvedValueOnce({ data: { message: "API keys updated" } } as never);

    const result = await putApiKeys({ openai: "sk-typed" });

    expect(mockApi.put).toHaveBeenCalledWith("/settings/api-keys", { openai: "sk-typed" });
    expect(result).toBeUndefined();
  });

  it("writes the server-key consents", async () => {
    mockApi.put.mockResolvedValueOnce({
      data: { server_key_consents: { openai: true } },
    } as never);

    const response = await putServerKeyConsents({ openai: true });

    expect(mockApi.put).toHaveBeenCalledWith("/settings/server-key-consents", { openai: true });
    expect(response.data.server_key_consents).toEqual({ openai: true });
  });

  it("reads the embedding index status of a campaign", async () => {
    mockApi.get.mockResolvedValueOnce({ data: { needs_retry: false } } as never);

    await getEmbeddingIndexStatus("c1");

    expect(mockApi.get).toHaveBeenCalledWith("/campaigns/c1/embedding-index");
  });

  it("retries and cancels a rebuild", async () => {
    mockApi.post.mockResolvedValue({ data: { needs_retry: false } } as never);

    await retryEmbeddingIndex("c1");
    await cancelEmbeddingIndex("c1");

    expect(mockApi.post).toHaveBeenCalledWith("/campaigns/c1/embedding-index/retry");
    expect(mockApi.post).toHaveBeenCalledWith("/campaigns/c1/embedding-index/cancel");
  });

  it("classifies failures without echoing the request body", () => {
    const secret = { response: { status: 400 }, config: { data: { openai: "sk-secret" } } };

    expect(classifySettingsError(secret)).toBe("validation");
    expect(classifySettingsError({ response: { status: 401 } })).toBe("unauthorized");
    expect(classifySettingsError({ response: { status: 409 } })).toBe("conflict");
    expect(classifySettingsError({ response: { status: 503 } })).toBe("server");
    expect(classifySettingsError(new Error("offline"))).toBe("network");
  });
});
