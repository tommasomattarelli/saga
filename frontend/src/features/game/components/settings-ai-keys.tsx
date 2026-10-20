import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../../../shared/stores/auth-store";
import type { KeyProvider, SettingsPolicy } from "../api/settings-api";
import { ActionButton, ErrorNote, Field, SubHeader, TextInput } from "./settings-fields";

const KEY_PROVIDERS: KeyProvider[] = ["openai", "openrouter", "google"];

interface SettingsAiKeysProps {
  policy: SettingsPolicy;
  hasKey: (provider: KeyProvider) => boolean;
  consents: Record<string, boolean>;
  onConsentChange: (provider: string, enabled: boolean) => void;
  consentSaving: boolean;
  consentError: string | null;
  saveKey: (provider: KeyProvider, key: string) => Promise<boolean>;
  keySaving: boolean;
  keyError: string | null;
  open: boolean;
}

export function SettingsAiKeys(props: SettingsAiKeysProps) {
  const { t } = useTranslation();
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  /* The typed key lives in this component only, and never survives a close,
     a sign-out or a different user. */
  useEffect(() => {
    setDrafts({});
  }, [props.open, userId]);

  const providers = KEY_PROVIDERS.filter((provider) =>
    props.policy.allowed_providers.includes(provider),
  );

  const handleSave = async (provider: KeyProvider) => {
    const value = (drafts[provider] ?? "").trim();
    if (!value) return;
    const saved = await props.saveKey(provider, value);
    if (saved) setDrafts((current) => ({ ...current, [provider]: "" }));
  };

  return (
    <div className="mb-4">
      <SubHeader label={t("settings.ai.keys_title")} />
      <p className="mb-2 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
        {t("settings.ai.keys_intro")}
      </p>

      {providers.map((provider) => {
        const inputId = `key-${provider}`;
        return (
          <div key={provider} className="mb-3">
            <Field
              label={t(`settings.ai.${provider}`)}
              htmlFor={inputId}
              hint={
                props.hasKey(provider) ? t("settings.ai.key_present") : t("settings.ai.key_absent")
              }
            >
              <TextInput
                id={inputId}
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={drafts[provider] ?? ""}
                placeholder={t("settings.ai.key_placeholder")}
                onChange={(e) =>
                  setDrafts((current) => ({ ...current, [provider]: e.target.value }))
                }
              />
            </Field>
            <ActionButton
              onClick={() => void handleSave(provider)}
              disabled={props.keySaving || !(drafts[provider] ?? "").trim()}
            >
              {props.keySaving ? t("settings.ai.saving") : t("settings.ai.key_save")}
            </ActionButton>
          </div>
        );
      })}

      <p className="mt-1 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
        {t("settings.ai.key_replace_note")}
      </p>
      {props.keyError ? <ErrorNote>{t(`settings.ai.error_${props.keyError}`)}</ErrorNote> : null}

      <div className="mt-4">
        <SubHeader label={t("settings.ai.consent_title")} />
        <p className="mb-2 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
          {t("settings.ai.consent_intro")}
        </p>
        {providers.map((provider) => {
          const sharing = props.policy.server_key_sharing[provider] === true;
          const consented = props.consents[provider] === true;
          const checkboxId = `consent-${provider}`;
          return (
            <div key={provider} className="mb-2">
              <label
                htmlFor={checkboxId}
                className="flex items-center gap-2 font-display text-xs"
                style={{ color: "var(--ink-secondary)" }}
              >
                <input
                  id={checkboxId}
                  type="checkbox"
                  /* A consent already given can always be revoked; a new one
                     needs the operator to share a key. */
                  disabled={props.consentSaving || (!sharing && !consented)}
                  checked={consented}
                  onChange={(e) => props.onConsentChange(provider, e.target.checked)}
                />
                {t("settings.ai.consent_allow", {
                  provider: t(`settings.ai.${provider}`, { defaultValue: provider }),
                })}
              </label>
              {sharing ? null : (
                <p className="ml-5 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
                  {t("settings.ai.consent_unavailable", {
                    provider: t(`settings.ai.${provider}`, { defaultValue: provider }),
                  })}
                </p>
              )}
            </div>
          );
        })}
        {props.consentError ? (
          <ErrorNote>{t(`settings.ai.error_${props.consentError}`)}</ErrorNote>
        ) : null}
        {props.consentSaving ? (
          <p className="mt-1 font-display text-[10px]" style={{ color: "var(--ink-faded)" }}>
            {t("settings.ai.saving")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
