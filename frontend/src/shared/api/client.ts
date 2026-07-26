import axios from "axios";
import { useAuthStore } from "../stores/auth-store";
import type { Campaign, TokenPair, TurnResponse, User } from "../types";
import { refreshMutex } from "./refresh-mutex";

type JournalTurn = Pick<
  TurnResponse,
  "turn_number" | "player_action" | "narration" | "dice_rolls" | "scene_mood"
>;

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        useAuthStore.getState().logout();
        return Promise.reject(error);
      }
      error.config._retry = true;
      try {
        const newAccessToken = await refreshMutex(refreshToken);
        error.config.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(error.config);
      } catch {
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(error);
  },
);

export const register = (username: string, email: string, password: string) =>
  api.post<TokenPair>("/auth/register", { username, email, password });

export const login = (username: string, password: string) =>
  api.post<TokenPair>("/auth/login", { username, password });

export const getMe = () => api.get<User>("/auth/me");

export const getCampaigns = () => api.get<Campaign[]>("/campaigns");

export const getCampaign = (id: string) => api.get<Campaign>(`/campaigns/${id}`);

export const deleteCampaign = (id: string) => api.delete(`/campaigns/${id}`);

export const createCampaign = (data: {
  world_id: string;
  name: string;
  death_mode: string;
  character_data?: Record<string, unknown>;
}) => api.post<Campaign>("/campaigns", data);

export const submitAction = (campaignId: string, action: string) =>
  api.post<TurnResponse>(`/campaigns/${campaignId}/action`, { action });

export interface WorldOption {
  slug: string;
  name: string;
  description: string;
  author: string;
  version: string;
  tags: string[];
}

export const getWorlds = () => api.get<WorldOption[]>("/worlds");

export interface EditableNode {
  slug: string;
  parent: string | null;
  kind: string;
  name: string;
  description?: string;
  position?: { x: number; y: number };
  elevation_m?: number;
  terrain?: string;
  km_per_unit?: number;
  map_image?: string;
  params?: Record<string, number | string | boolean>;
  items?: { name: string; qty?: number; notes?: string }[];
  exits?: { to: string; locked?: boolean; hidden?: boolean; notes?: string }[];
}

export interface ParamDef {
  name: string;
  type?: "int" | "float" | "str" | "bool";
  required?: boolean;
  min?: number;
  max?: number;
}

export interface PsychologyAxis {
  range: [number, number];
  default: number;
  bands: { min: number; label: string }[];
}

export interface PsychologyDef {
  first_impression_multiplier: number;
  max_delta_per_turn: number;
  axes: Record<string, PsychologyAxis>;
}

export interface NpcFieldDef {
  name: string;
  default?: string;
  scene?: boolean;
}

export interface EditableWorld {
  slug: string;
  meta: { name: string; author: string; version: string; description: string; tags: string[] };
  root: Record<string, unknown> & { kind: string; description?: string };
  taxonomy: {
    kinds: { name: string; scale: "outdoor" | "interior"; params?: ParamDef[] }[];
    terrains: { name: string; travel_multiplier: number }[];
    travel_modes: { name: string; speed_kmh: number }[];
    defaults?: { terrain?: string | null; elevation_m?: number };
    psychology?: PsychologyDef | null;
    npc_fields?: NpcFieldDef[] | null;
  };
  scenario: Record<string, unknown> | null;
  nodes: EditableNode[];
  edges: Record<string, unknown>[];
  factions: Record<string, unknown>[];
  npcs: Record<string, unknown>[];
  encounters: Record<string, unknown>[];
}

export const getWorld = (slug: string) => api.get<EditableWorld>(`/worlds/${slug}`);

export const createWorld = (data: { name: string; author?: string; description?: string }) =>
  api.post<WorldOption>("/worlds", data);

export const saveWorld = (slug: string, payload: EditableWorld) =>
  api.put<WorldOption>(`/worlds/${slug}`, payload);

export const deleteWorld = (slug: string) => api.delete(`/worlds/${slug}`);

export const exportWorld = (slug: string) =>
  api.get<Blob>(`/worlds/${slug}/export`, { responseType: "blob" });

export const importWorld = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<WorldOption>("/worlds/import", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export interface MapNode {
  name: string;
  kind: string;
  scale: "outdoor" | "interior";
  position: { x: number; y: number } | null;
  parent: string | null;
  children: string[];
  has_status: boolean;
}

export interface MapData {
  root: string;
  player_position: string | null;
  nodes: Record<string, MapNode>;
  edges: { from: string; to: string; mode: string }[];
}

export const getCampaignMap = (campaignId: string) =>
  api.get<MapData>(`/campaigns/${campaignId}/map`);

export const getTurns = (campaignId: string) =>
  api.get<JournalTurn[]>(`/journal/${campaignId}`, { params: { limit: 200, offset: 0 } });

export default api;
