import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ProfilePatch } from "../api/settings-api";
import {
  ActionButton,
  ErrorNote,
  Field,
  SelectInput,
  SubHeader,
  TextInput,
} from "./settings-fields";

const CREDENTIAL_COPY: Record<string, string> = {
  personal: "settings.ai.credential_personal",
  server: "settings.ai.credential_server",
  missing: "settings.ai.credential_missing",
  not_required: "settings.ai.credential_not_required",
};

interface ProfileEditorProps {
  kind: "generation" | "embedding";
  title: string;
  provider: string | null;
  model: string | null;
  localEndpoint: string | null;
  allowedProviders: string[];
  localEndpoints: string[];
  inUseProvider: string;
  inUseModel: string;
  credentialSource: string;
  saving: boolean;
  errorMessage: string | null;
  onSave: (patch: ProfilePatch) => void;
}

export function ProfileEditor(props: ProfileEditorProps) {
  const { t } = useTranslation();
  const [provider, setProvider] = useState(props.provider ?? "");
  const [model, setModel] = useState(props.model ?? "");
  const [endpoint, setEndpoint] = useState(props.localEndpoint ?? "");

  /* The draft follows the stored profile: a save of THIS editor brings the
     values back from the server, a save of the other editor leaves them
     untouched. */
  useEffect(() => {
    setProvider(props.provider ?? "");
    setModel(props.model ?? "");
    setEndpoint(props.localEndpoint ?? "");
  }, [props.provider, props.model, props.localEndpoint]);

  const isLocal = provider === "local";
  const inherits = provider === "";
  const options = props.allowedProviders.includes(provider)
    ? props.allowedProviders
    : [...props.allowedProviders, provider].filter(Boolean);

  const modelMissing = !inherits && model.trim() === "";
  const endpointMissing = isLocal && endpoint === "";
  const canSave = !modelMissing && !endpointMissing && !props.saving;

  const patchFor = (
    nextProvider: string,
    nextModel: string,
    nextEndpoint: string,
  ): ProfilePatch => {
    if (props.kind === "generation") {
      return {
        generation_provider: nextProvider || null,
        generation_model: nextProvider ? nextModel.trim() : null,
        generation_local_endpoint: nextProvider === "local" ? nextEndpoint : null,
      };
    }
    return {
      embedding_provider: nextProvider || null,
      embedding_model: nextProvider ? nextModel.trim() : null,
      embedding_local_endpoint: nextProvider === "local" ? nextEndpoint : null,
    };
  };

  const handleSave = () => {
    if (!canSave) return;
    props.onSave(patchFor(provider, model, endpoint));
  };

  /* The draft is cleared only by the server answer: a refused save keeps
     everything the player typed. */
  const handleUseDefault = () => {
    props.onSave(patchFor("", "", ""));
  };

  const providerLabel = (id: string) => t(`settings.ai.${id}`, { defaultValue: id });

  return (
    <div className="mb-4">
      <SubHeader label={props.title} />
      <p className="mb-2 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
        {t("settings.ai.currently", {
          provider: props.inUseProvider,
          model: props.inUseModel,
        })}
      </p>
      <p className="mb-2 font-display text-[11px]" style={{ color: "var(--ink-faded)" }}>
        {t(CREDENTIAL_COPY[props.credentialSource] ?? "settings.ai.credential_missing")}
      </p>

      <Field label={t("settings.ai.provider")} htmlFor={`${props.kind}-provider`}>
        <SelectInput
          id={`${props.kind}-provider`}
          value={provider}
          onChange={(e) => {
            const next = e.target.value;
            setProvider(next);
            if (next !== "local") setEndpoint("");
            if (!next) setModel("");
          }}
        >
          <option value="">{t("settings.ai.inherit")}</option>
          {options.map((id) => (
            <option key={id} value={id}>
              {providerLabel(id)}
            </option>
          ))}
        </SelectInput>
      </Field>

      <Field
        label={t("settings.ai.model")}
        htmlFor={`${props.kind}-model`}
        hint={inherits ? t("settings.ai.model_inherit_hint") : undefined}
      >
        <TextInput
          id={`${props.kind}-model`}
          value={model}
          disabled={inherits}
          placeholder={inherits ? t("settings.ai.model_inherit_placeholder") : ""}
          onChange={(e) => setModel(e.target.value)}
        />
      </Field>

      {isLocal ? (
        <Field label={t("settings.ai.local_endpoint")} htmlFor={`${props.kind}-endpoint`}>
          <SelectInput
            id={`${props.kind}-endpoint`}
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
          >
            <option value="">{t("settings.ai.endpoint_choose")}</option>
            {props.localEndpoints.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </SelectInput>
        </Field>
      ) : null}

      {modelMissing ? <ErrorNote>{t("settings.ai.model_required")}</ErrorNote> : null}
      {endpointMissing ? <ErrorNote>{t("settings.ai.endpoint_required")}</ErrorNote> : null}
      {props.errorMessage ? <ErrorNote>{props.errorMessage}</ErrorNote> : null}

      <div className="mt-2 flex gap-2">
        <ActionButton onClick={handleSave} disabled={!canSave} tone="primary">
          {props.saving ? t("settings.ai.saving") : t("settings.ai.save")}
        </ActionButton>
        <ActionButton onClick={handleUseDefault} disabled={props.saving || inherits}>
          {t("settings.ai.use_default")}
        </ActionButton>
      </div>
    </div>
  );
}
