import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { classifySettingsError } from "../api/settings-api";
import { useEmbeddingIndexActions, useEmbeddingIndexStatus } from "../hooks/use-embedding-index";
import { ActionButton, ErrorNote, SubHeader } from "./settings-fields";

interface SettingsEmbeddingIndexProps {
  campaignId: string | null;
  enabled: boolean;
  conflict?: boolean;
}

export function SettingsEmbeddingIndex(props: SettingsEmbeddingIndexProps) {
  const { t } = useTranslation();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  /* The confirmation belongs to one user, one campaign and one target index:
     a new target asks for a new confirmation. */
  const [confirmedScope, setConfirmedScope] = useState<string | null>(null);
  const query = useEmbeddingIndexStatus(props.campaignId, props.enabled);
  const actions = useEmbeddingIndexActions();

  if (!props.campaignId) {
    return (
      <div className="mb-4">
        <SubHeader label={t("settings.ai.index_title")} />
        <p className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
          {t("settings.ai.index_hint_no_campaign")}
        </p>
      </div>
    );
  }

  const status = query.data;
  const active = status?.active ?? null;
  const target = status?.target ?? null;
  const progress = status?.progress ?? null;
  const scope = `${userId ?? ""}|${props.campaignId}|${target?.id ?? ""}`;
  const confirming = confirmedScope !== null && confirmedScope === scope;

  const inScope = (mutation: { variables?: { scopeUserId: string | null } }) =>
    mutation.variables?.scopeUserId === userId;
  const busy =
    (actions.retry.isPending && inScope(actions.retry)) ||
    (actions.cancel.isPending && inScope(actions.cancel));
  const failedAction = [actions.retry, actions.cancel].find(
    (mutation) => mutation.error && inScope(mutation),
  );
  const actionError = failedAction?.error ?? null;

  const cancelRebuild = () => {
    setConfirmedScope(null);
    actions.cancel.mutate({ scopeUserId: userId, scopeCampaignId: props.campaignId });
  };

  const retryRebuild = () => {
    actions.retry.mutate({ scopeUserId: userId, scopeCampaignId: props.campaignId });
  };

  return (
    <div className="mb-4">
      <SubHeader label={t("settings.ai.index_title")} />

      {props.conflict ? (
        <div className="mb-2">
          <ErrorNote>{t("settings.ai.error_conflict")}</ErrorNote>
          <p className="mt-1 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
            {t("settings.ai.error_conflict_hint")}
          </p>
        </div>
      ) : null}

      {query.isLoading ? (
        <p className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
          {t("settings.ai.index_loading")}
        </p>
      ) : null}

      {query.error ? (
        <div className="mb-2">
          <ErrorNote>{t("settings.ai.index_error")}</ErrorNote>
        </div>
      ) : null}

      {active ? (
        <div className="mb-2">
          <p className="font-display text-xs" style={{ color: "var(--ink-secondary)" }}>
            {t("settings.ai.index_active", {
              provider: active.provider,
              model: active.model,
            })}
          </p>
          <p className="font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
            {active.dimension === null
              ? t("settings.ai.index_dimension_unknown")
              : t("settings.ai.index_dimension", { dimension: active.dimension })}
          </p>
        </div>
      ) : null}

      {target ? (
        <div className="mb-2">
          <p className="font-display text-xs" style={{ color: "var(--ink-secondary)" }}>
            {t("settings.ai.index_target", {
              provider: target.provider,
              model: target.model,
              state: target.state,
            })}
          </p>
        </div>
      ) : null}

      {!active && !target && !query.isLoading && !query.error ? (
        <p className="mb-2 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
          {t("settings.ai.index_none")}
        </p>
      ) : null}

      {progress ? (
        <div className="mb-2">
          <p className="font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
            {t("settings.ai.index_progress", {
              embedded: progress.embedded,
              total: progress.total,
              pending: progress.pending,
              failed: progress.failed,
            })}
          </p>
          <p className="font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
            {t("settings.ai.index_sources", {
              turns: progress.turn_total,
              facts: progress.fact_total,
            })}
          </p>
        </div>
      ) : null}

      {status?.suspended_reason ? (
        <div className="mb-2">
          <ErrorNote>{status.suspended_reason}</ErrorNote>
        </div>
      ) : null}

      {actionError ? (
        <div className="mb-2">
          <ErrorNote>{t(`settings.ai.error_${classifySettingsError(actionError)}`)}</ErrorNote>
        </div>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-2">
        <ActionButton onClick={() => void query.refetch()} disabled={busy}>
          {t("settings.ai.index_refresh")}
        </ActionButton>
        <ActionButton onClick={retryRebuild} disabled={busy || !status?.needs_retry}>
          {t("settings.ai.index_retry")}
        </ActionButton>
        {confirming ? (
          <ActionButton onClick={cancelRebuild} disabled={busy} tone="primary">
            {t("settings.ai.index_confirm_cancel")}
          </ActionButton>
        ) : (
          <ActionButton onClick={() => setConfirmedScope(scope)} disabled={busy || !target}>
            {t("settings.ai.index_cancel")}
          </ActionButton>
        )}
      </div>
      {busy ? (
        <p className="mt-1 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
          {t("settings.ai.saving")}
        </p>
      ) : null}
    </div>
  );
}
