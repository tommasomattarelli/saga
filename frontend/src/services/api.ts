import axios from "axios";
import { useAuthStore } from "../stores/auth-store";
import type {
  Campaign,
  TokenPair,
  TurnResponse,
  User,
  SavePoint,
} from "../types";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// Attach auth token to requests
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 - try refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken && !error.config._retry) {
        error.config._retry = true;
        try {
          const { data } = await axios.post<TokenPair>("/api/auth/refresh", {
            refresh_token: refreshToken,
          });
          useAuthStore.getState().setTokens(data);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api(error.config);
        } catch {
          useAuthStore.getState().logout();
        }
      }
    }
    return Promise.reject(error);
  },
);

// Auth
export const register = (username: string, email: string, password: string) =>
  api.post<TokenPair>("/auth/register", { username, email, password });

export const login = (username: string, password: string) =>
  api.post<TokenPair>("/auth/login", { username, password });

export const getMe = () => api.get<User>("/auth/me");

// Campaigns
export const getCampaigns = () => api.get<Campaign[]>("/campaigns");

export const getCampaign = (id: string) => api.get<Campaign>(`/campaigns/${id}`);

export const createCampaign = (data: {
  template_id: string;
  name: string;
  death_mode: string;
  character_data?: Record<string, unknown>;
}) => api.post<Campaign>("/campaigns", data);

export const submitTurn = (campaignId: string, action: string) =>
  api.post<TurnResponse>(`/campaigns/${campaignId}/turn`, { action });

// Saves
export const getSaves = (campaignId: string) =>
  api.get<SavePoint[]>(`/saves/${campaignId}`);

export const createSave = (campaignId: string, name: string) =>
  api.post<SavePoint>(`/saves/${campaignId}`, { name });

export const loadSave = (campaignId: string, saveId: string) =>
  api.post(`/saves/${campaignId}/load/${saveId}`);

// Journal
export const getJournal = (campaignId: string, limit = 50, offset = 0) =>
  api.get(`/journal/${campaignId}`, { params: { limit, offset } });

// Settings
export const getSettings = () => api.get("/settings");

export const updateApiKeys = (keys: Record<string, string>) =>
  api.put("/settings/api-keys", keys);

// Export
export const exportCampaign = (campaignId: string) =>
  api.get(`/export/${campaignId}`);

export default api;
