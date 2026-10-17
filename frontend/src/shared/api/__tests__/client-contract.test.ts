import axios, { AxiosError, AxiosHeaders } from "axios";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import api, {
  createCampaign,
  createWorld,
  deleteCampaign,
  deleteWorld,
  exportWorld,
  getCampaign,
  getCampaignMap,
  getCampaigns,
  getMe,
  getTurns,
  getWorld,
  getWorlds,
  importWorld,
  login,
  register,
  saveWorld,
  submitAction,
} from "../client";
import type { EditableWorld } from "../client";
import { useAuthStore } from "../../stores/auth-store";

const instanceAdapter = api.defaults.adapter;
const globalAdapter = axios.defaults.adapter;
let requests: InternalAxiosRequestConfig[];

function response(
  config: InternalAxiosRequestConfig,
  data: unknown = { ok: true },
  status = 200,
): AxiosResponse<unknown> {
  return { config, data, status, statusText: String(status), headers: new AxiosHeaders() };
}

function rejectUnauthorized(config: InternalAxiosRequestConfig): never {
  throw new AxiosError(
    "Unauthorized",
    "ERR_BAD_REQUEST",
    config,
    undefined,
    response(config, {}, 401),
  );
}

function useAdapter(handler: AxiosAdapter) {
  const adapter: AxiosAdapter = async (config) => {
    requests.push(config);
    return handler(config);
  };
  api.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
}

beforeEach(() => {
  requests = [];
  useAuthStore.setState({ accessToken: null, refreshToken: null });
  useAdapter(async (config) => response(config));
});

afterEach(() => {
  api.defaults.adapter = instanceAdapter;
  axios.defaults.adapter = globalAdapter;
});

describe("API wire contracts", () => {
  const reads: [() => Promise<unknown>, string][] = [
    [getMe, "/auth/me"],
    [getCampaigns, "/campaigns"],
    [() => getCampaign("campaign"), "/campaigns/campaign"],
    [getWorlds, "/worlds"],
    [() => getWorld("world"), "/worlds/world"],
    [() => getCampaignMap("campaign"), "/campaigns/campaign/map"],
  ];

  it.each(reads)("dispatches the expected read endpoint %#", async (read, path) => {
    await read();
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ method: "get", url: path });
    expect(requests[0].headers.has("Authorization")).toBe(false);
  });

  it("serializes registration, login, campaign creation and turn actions", async () => {
    await register("player", "player@example.com", "secret");
    await login("player", "secret");
    await createCampaign({
      world_id: "world",
      name: "Adventure",
      difficulty: "medium",
      character_data: { name: "Aria" },
    });
    await submitAction("campaign", "Open the door");

    expect(
      requests.map(({ method, url, data }) => [method, url, JSON.parse(String(data))]),
    ).toEqual([
      [
        "post",
        "/auth/register",
        { username: "player", email: "player@example.com", password: "secret" },
      ],
      ["post", "/auth/login", { username: "player", password: "secret" }],
      [
        "post",
        "/campaigns",
        {
          world_id: "world",
          name: "Adventure",
          difficulty: "medium",
          character_data: { name: "Aria" },
        },
      ],
      ["post", "/campaigns/campaign/action", { action: "Open the door" }],
    ]);
  });

  it("creates and saves worlds and dispatches deletion endpoints", async () => {
    const world: EditableWorld = {
      slug: "world",
      meta: { name: "World", author: "Author", version: "1", description: "", tags: [] },
      root: { kind: "world" },
      taxonomy: {
        kinds: [{ name: "world", scale: "outdoor" }],
        terrains: [],
        travel_modes: [],
      },
      scenario: null,
      nodes: [],
      edges: [],
      factions: [],
      npcs: [],
      encounters: [],
    };
    await createWorld({ name: "World", author: "Author" });
    await saveWorld("world", world);
    await deleteWorld("world");
    await deleteCampaign("campaign");

    expect(JSON.parse(String(requests[0].data))).toEqual({ name: "World", author: "Author" });
    expect(requests[1]).toMatchObject({ method: "put", url: "/worlds/world" });
    expect(JSON.parse(String(requests[1].data))).toEqual(world);
    expect(requests.slice(2).map(({ method, url }) => [method, url])).toEqual([
      ["delete", "/worlds/world"],
      ["delete", "/campaigns/campaign"],
    ]);
  });

  it("keeps archive downloads binary and uploads multipart files", async () => {
    await exportWorld("world");
    expect(requests[0]).toMatchObject({ url: "/worlds/world/export", responseType: "blob" });
    const file = new File(["archive"], "world.zip", { type: "application/zip" });
    await importWorld(file);
    const form = requests[1].data as FormData;
    expect(requests[1]).toMatchObject({ method: "post", url: "/worlds/import" });
    expect(form.get("file")).toBeInstanceOf(File);
    expect((form.get("file") as File).name).toBe("world.zip");
  });

  it("requests the journal pagination contract", async () => {
    await getTurns("campaign");
    expect(requests[0]).toMatchObject({
      url: "/journal/campaign",
      params: { limit: 200, offset: 0 },
    });
  });
});

describe("Authentication interception with the real HTTP client", () => {
  it("attaches the memory-only access token", async () => {
    useAuthStore.setState({ accessToken: "access" });
    await getMe();
    expect(requests[0].headers.get("Authorization")).toBe("Bearer access");
  });

  it("refreshes once and retries a rejected request using the new token", async () => {
    useAuthStore.setState({ accessToken: "old", refreshToken: "refresh" });
    let attempts = 0;
    useAdapter(async (config) => {
      if (config.url === "/api/auth/refresh") {
        expect(JSON.parse(String(config.data))).toEqual({ refresh_token: "refresh" });
        return response(config, {
          access_token: "new",
          refresh_token: "next",
          token_type: "bearer",
        });
      }
      if (++attempts === 1) rejectUnauthorized(config);
      expect(config.headers.get("Authorization")).toBe("Bearer new");
      return response(config);
    });

    await getCampaigns();
    expect(requests).toHaveLength(3);
    expect(useAuthStore.getState().accessToken).toBe("new");
  });

  it("logs out instead of refreshing when no refresh token exists", async () => {
    useAuthStore.setState({ accessToken: "expired" });
    useAdapter(async (config) => rejectUnauthorized(config));
    await expect(getMe()).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests).toHaveLength(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("logs out after a refresh failure without retrying the original request", async () => {
    useAuthStore.setState({ accessToken: "expired", refreshToken: "invalid" });
    useAdapter(async (config) => rejectUnauthorized(config));
    await expect(getMe()).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests).toHaveLength(2);
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });

  it("never loops when the retried request is also unauthorized", async () => {
    useAuthStore.setState({ accessToken: "expired", refreshToken: "refresh" });
    useAdapter(async (config) =>
      config.url === "/api/auth/refresh"
        ? response(config, { access_token: "new", refresh_token: "next", token_type: "bearer" })
        : rejectUnauthorized(config),
    );
    await expect(getMe()).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests).toHaveLength(3);
  });

  it("propagates network errors without attempting token refresh", async () => {
    useAdapter(async (config) => {
      throw new AxiosError("Connection failed", "ERR_NETWORK", config);
    });
    await expect(getMe()).rejects.toMatchObject({ code: "ERR_NETWORK" });
    expect(requests).toHaveLength(1);
  });
});
