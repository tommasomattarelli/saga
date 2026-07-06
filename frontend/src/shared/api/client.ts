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
