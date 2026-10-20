import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { useGameStore } from "../../../shared/stores/game-store";
import {
  classifySettingsError,
  type KeyProvider,
  type ProfilePatch,
  type SettingsErrorKind,
} from "../api/settings-api";
import {
  settingsQueryKey,
  useAiSettings,
  useSaveConsent,
  useSaveProfiles,
} from "../hooks/use-ai-settings";
import { useApiKeySaver } from "../hooks/use-api-keys";
import { embeddingIndexQueryKey } from "../hooks/use-embedding-index";
import { ProfileEditor } from "./settings-ai-profiles";
import { SettingsAiKeys } from "./settings-ai-keys";
import { SettingsEmbeddingIndex } from "./settings-embedding-index";
import { ErrorNote } from "./settings-fields";

/* Only the error of the session that sent the request may be shown. */
function scopedError(
  mutation: { error: Error | null; variables?: { scopeUserId: string | null } },
  userId: string | null,
): SettingsErrorKind | null {
  if (!mutation.error) return null;
  if (!mutation.variables || mutation.variables.scopeUserId !== userId) return null;
  return classifySettingsError(mutation.error);
}

export default function SettingsAiPanel({ open }: { open: boolean }) {
  const { t } = useTranslation();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const campaignId = useGameStore((s) => s.campaign?.id ?? null);
  const queryClient = useQueryClient();

  const active = open && isAuthenticated && !!userId;
  const settingsQuery = useAiSettings(active);
  const saveGeneration = useSaveProfiles();
  const saveEmbedding = useSaveProfiles();
  const saveConsent = useSaveConsent();
  const keySaver = useApiKeySaver();

  /* One user's settings must never surface for the next one. */
  const previousUser = useRef(userId);
  useEffect(() => {
    if (previousUser.current !== userId) {
      queryClient.removeQueries({ queryKey: settingsQueryKey(previousUser.current) });
      queryClient.removeQueries({
        queryKey: embeddingIndexQueryKey(previousUser.current, null),
      });
      previousUser.current = userId;
    }
  }, [userId, queryClient]);

  const settings = settingsQuery.data;

  const handleSave = (kind: "generation" | "embedding", patch: ProfilePatch) => {
    const scopeUserId = userId;
    const mutation = kind === "generation" ? saveGeneration : saveEmbedding;
    mutation.mutate({ patch, scopeUserId });
  };

  const generationError = scopedError(saveGeneration, userId);
  const embeddingError = scopedError(saveEmbedding, userId);
  const consentError = scopedError(saveConsent, userId);
  const conflict = embeddingError === "conflict";

  if (!active) return null;

  if (settingsQuery.isLoading) {
    return (
      <p className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
        {t("settings.ai.loading")}
      </p>
    );
  }

  if (settingsQuery.error || !settings) {
    return <ErrorNote>{t("settings.ai.load_error")}</ErrorNote>;
  }

  const policy = settings.policy;
  const generationInUse = settings.generation_provider
    ? { provider: settings.generation_provider, model: settings.generation_model ?? "" }
    : {
        provider: policy.generation_default.provider,
        model: policy.generation_default.model,
      };
  const embeddingInUse = settings.embedding_provider
    ? { provider: settings.embedding_provider, model: settings.embedding_model ?? "" }
    : {
        provider: policy.embedding_default.provider,
        model: policy.embedding_default.model,
      };

  const hasKey = (provider: KeyProvider) =>
    provider === "openai"
      ? settings.has_openai_key
      : provider === "openrouter"
        ? settings.has_openrouter_key
        : settings.has_google_key;

  return (
    <div>
      <ProfileEditor
        kind="generation"
        title={t("settings.ai.generation_title")}
        provider={settings.generation_provider}
        model={settings.generation_model}
        localEndpoint={settings.generation_local_endpoint}
        allowedProviders={policy.allowed_providers}
        localEndpoints={policy.local_endpoints}
        inUseProvider={generationInUse.provider}
        inUseModel={generationInUse.model}
        credentialSource={settings.credential_source}
        saving={saveGeneration.isPending}
        errorMessage={generationError ? t(`settings.ai.error_${generationError}`) : null}
        onSave={(patch) => handleSave("generation", patch)}
      />

      <ProfileEditor
        kind="embedding"
        title={t("settings.ai.embedding_title")}
        provider={settings.embedding_provider}
        model={settings.embedding_model}
        localEndpoint={settings.embedding_local_endpoint}
        allowedProviders={policy.allowed_providers}
        localEndpoints={policy.local_endpoints}
        inUseProvider={embeddingInUse.provider}
        inUseModel={embeddingInUse.model}
        credentialSource={settings.embedding_credential_source}
        saving={saveEmbedding.isPending}
        errorMessage={embeddingError ? t(`settings.ai.error_${embeddingError}`) : null}
        onSave={(patch) => handleSave("embedding", patch)}
      />

      <SettingsAiKeys
        policy={policy}
        hasKey={hasKey}
        consents={settings.server_key_consents}
        onConsentChange={(provider, enabled) =>
          saveConsent.mutate({ provider, enabled, scopeUserId: userId })
        }
        consentSaving={saveConsent.isPending}
        consentError={consentError}
        saveKey={keySaver.save}
        keySaving={keySaver.isSaving}
        keyError={keySaver.error}
        open={open}
      />

      <SettingsEmbeddingIndex campaignId={campaignId} enabled={active} conflict={conflict} />
    </div>
  );
}
