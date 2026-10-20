import api from "../../../shared/api/client";

interface ProfileDefaults {
  provider: string;
  model: string;
  local_endpoint: string | null;
}

export interface SettingsPolicy {
  allowed_providers: string[];
  local_endpoints: string[];
  generation_default: ProfileDefaults;
  embedding_default: ProfileDefaults;
  server_key_sharing: Record<string, boolean>;
}

export interface SettingsResponse {
  preferred_language: string;
  generation_provider: string | null;
  generation_model: string | null;
  generation_local_endpoint: string | null;
  embedding_provider: string | null;
  embedding_model: string | null;
  embedding_local_endpoint: string | null;
  server_key_consents: Record<string, boolean>;
  has_openai_key: boolean;
  has_openrouter_key: boolean;
  has_google_key: boolean;
  effective_provider: string;
  credential_source: string;
  effective_embedding_provider: string;
  embedding_credential_source: string;
  policy: SettingsPolicy;
}

export type ProfilePatch = {
  generation_provider?: string | null;
  generation_model?: string | null;
  generation_local_endpoint?: string | null;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  embedding_local_endpoint?: string | null;
};

export type KeyProvider = "openai" | "openrouter" | "google";

export type ApiKeysUpdate = Partial<Record<KeyProvider, string>>;

interface EmbeddingIndexSummary {
  id: string;
  provider: string;
  model: string;
  endpoint_name: string | null;
  pipeline_version: string;
  dimension: number | null;
  state: string;
  last_error: string | null;
}

interface EmbeddingIndexProgress {
  total: number;
  embedded: number;
  pending: number;
  failed: number;
  turn_total: number;
  fact_total: number;
}

export interface EmbeddingIndexStatus {
  active: EmbeddingIndexSummary | null;
  target: EmbeddingIndexSummary | null;
  latest: EmbeddingIndexSummary | null;
  progress: EmbeddingIndexProgress | null;
  suspended_reason: string | null;
  needs_retry: boolean;
}

export type SettingsErrorKind = "unauthorized" | "conflict" | "validation" | "server" | "network";

export const getSettings = () => api.get<SettingsResponse>("/settings");

export const patchSettings = (patch: ProfilePatch) =>
  api.patch<SettingsResponse>("/settings", patch);

export const putServerKeyConsents = (consents: Record<string, boolean>) =>
  api.put<{ server_key_consents: Record<string, boolean> }>(
    "/settings/server-key-consents",
    consents,
  );

/* Write-only: the response carries no key material and is dropped here, so no
   caller can keep the raw Axios payload around. */
export const putApiKeys = async (keys: ApiKeysUpdate): Promise<void> => {
  await api.put("/settings/api-keys", keys);
};

export const getEmbeddingIndexStatus = (campaignId: string) =>
  api.get<EmbeddingIndexStatus>(`/campaigns/${campaignId}/embedding-index`);

export const retryEmbeddingIndex = (campaignId: string) =>
  api.post<EmbeddingIndexStatus>(`/campaigns/${campaignId}/embedding-index/retry`);

export const cancelEmbeddingIndex = (campaignId: string) =>
  api.post<EmbeddingIndexStatus>(`/campaigns/${campaignId}/embedding-index/cancel`);

const statusOf = (error: unknown): number | undefined => {
  if (typeof error !== "object" || error === null) return undefined;
  const response = (error as { response?: { status?: number } }).response;
  return typeof response?.status === "number" ? response.status : undefined;
};

/* Only the status code is read: an Axios error carries the request body, and
   the request body may be the user's key. */
export const classifySettingsError = (error: unknown): SettingsErrorKind => {
  const status = statusOf(error);
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 409) return "conflict";
  if (status === 400 || status === 422) return "validation";
  if (status !== undefined && status >= 500) return "server";
  return "network";
};
