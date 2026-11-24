import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ProfilePatch, SettingsResponse } from "../api/settings-api";
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

type GenerationProfile = readonly [string | null, string | null, string | null];

const generationProfile = (
  provider: string | null | undefined,
  model: string | null | undefined,
  endpoint: string | null | undefined,
): GenerationProfile => {
  const selectedProvider = provider || null;
  return [
    selectedProvider,
    selectedProvider ? model?.trim() || null : null,
    selectedProvider === "local" ? endpoint || null : null,
  ];
};

const sameGenerationProfile = (left: GenerationProfile, right: GenerationProfile) =>
  left[0] === right[0] && left[1] === right[1] && left[2] === right[2];

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
  settingsResponse: SettingsResponse;
  saving: boolean;
  errorMessage: string | null;
  onSave: (patch: ProfilePatch) => Promise<SettingsResponse>;
}

interface FormatChoiceSubmission {
  fingerprint: string | null;
  revision: { json: number; prompt: number };
  targetRevision: number;
  submitted: { json: boolean; prompt: boolean };
  submittedProfile: GenerationProfile;
  baselineProfile: GenerationProfile;
  useDefault: boolean;
  baseline: SettingsResponse;
}

export function ProfileEditor(props: ProfileEditorProps) {
  const { t } = useTranslation();
  const [provider, setProvider] = useState(props.provider ?? "");
  const [model, setModel] = useState(props.model ?? "");
  const [endpoint, setEndpoint] = useState(props.localEndpoint ?? "");
  const [formatChoices, setFormatChoices] = useState({
    json: props.settingsResponse.generation_allow_json_mode_fallback,
    prompt: props.settingsResponse.generation_allow_prompt_only_fallback,
    dirty: { json: false, prompt: false },
  });
  const [pendingFormatSave, setPendingFormatSave] = useState<FormatChoiceSubmission | null>(null);
  const formatChoiceRevision = useRef({ json: 0, prompt: 0 });
  const profileTargetRevision = useRef(0);
  const fingerprint = useRef(props.settingsResponse.generation_format_fingerprint);
  const acknowledgedSettings = useRef<{
    baseline: SettingsResponse;
    response: SettingsResponse;
  } | null>(null);

  /* The draft follows the stored profile: a save of THIS editor brings the
     values back from the server, a save of the other editor leaves them
     untouched. */
  useEffect(() => {
    setProvider(props.provider ?? "");
    setModel(props.model ?? "");
    setEndpoint(props.localEndpoint ?? "");
  }, [props.provider, props.model, props.localEndpoint]);

  useEffect(() => {
    if (pendingFormatSave) return;
    const acknowledgement = acknowledgedSettings.current;
    if (acknowledgement) {
      if (props.settingsResponse === acknowledgement.response) acknowledgedSettings.current = null;
      else if (props.settingsResponse === acknowledgement.baseline) return;
      else acknowledgedSettings.current = null;
    }
    const currentFingerprint = props.settingsResponse.generation_format_fingerprint;
    const fingerprintChanged = fingerprint.current !== currentFingerprint;
    fingerprint.current = currentFingerprint;
    if (fingerprintChanged) {
      setFormatChoices({
        json: props.settingsResponse.generation_allow_json_mode_fallback,
        prompt: props.settingsResponse.generation_allow_prompt_only_fallback,
        dirty: { json: false, prompt: false },
      });
      return;
    }
    if (
      provider !== (props.provider ?? "") ||
      model !== (props.model ?? "") ||
      endpoint !== (props.localEndpoint ?? "")
    )
      return;
    setFormatChoices((current) => ({
      ...current,
      json: current.dirty.json
        ? current.json
        : props.settingsResponse.generation_allow_json_mode_fallback,
      prompt: current.dirty.prompt
        ? current.prompt
        : props.settingsResponse.generation_allow_prompt_only_fallback,
    }));
  }, [
    props.settingsResponse,
    props.provider,
    props.model,
    props.localEndpoint,
    provider,
    model,
    endpoint,
    pendingFormatSave,
  ]);

  const clearFormatChoices = () => {
    profileTargetRevision.current += 1;
    setFormatChoices({
      json: false,
      prompt: false,
      dirty: { json: false, prompt: false },
    });
  };

  const acknowledgeFormatChoices = (
    submission: FormatChoiceSubmission,
    response: SettingsResponse,
  ) => {
    const fingerprintChanged = submission.fingerprint !== response.generation_format_fingerprint;
    const responseProfile = generationProfile(
      response.generation_provider,
      response.generation_model,
      response.generation_local_endpoint,
    );
    const submittedProfileMatchesResponse = sameGenerationProfile(
      submission.submittedProfile,
      responseProfile,
    );
    const profileChanged = !sameGenerationProfile(
      submission.submittedProfile,
      submission.baselineProfile,
    );
    const preserveIntent =
      profileTargetRevision.current === submission.targetRevision &&
      (!fingerprintChanged ||
        (profileChanged && submittedProfileMatchesResponse && !submission.useDefault));
    acknowledgedSettings.current = { baseline: submission.baseline, response };
    fingerprint.current = response.generation_format_fingerprint;
    setFormatChoices((current) => {
      const keepJson =
        preserveIntent &&
        current.dirty.json &&
        (formatChoiceRevision.current.json !== submission.revision.json ||
          (!fingerprintChanged && !submission.submitted.json));
      const keepPrompt =
        preserveIntent &&
        current.dirty.prompt &&
        (formatChoiceRevision.current.prompt !== submission.revision.prompt ||
          (!fingerprintChanged && !submission.submitted.prompt));
      return {
        json: keepJson ? current.json : response.generation_allow_json_mode_fallback,
        prompt: keepPrompt ? current.prompt : response.generation_allow_prompt_only_fallback,
        dirty: { json: keepJson, prompt: keepPrompt },
      };
    });
    setPendingFormatSave(null);
  };

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
        ...(formatChoices.dirty.json
          ? { generation_allow_json_mode_fallback: formatChoices.json }
          : {}),
        ...(formatChoices.dirty.prompt
          ? { generation_allow_prompt_only_fallback: formatChoices.prompt }
          : {}),
      };
    }
    return {
      embedding_provider: nextProvider || null,
      embedding_model: nextProvider ? nextModel.trim() : null,
      embedding_local_endpoint: nextProvider === "local" ? nextEndpoint : null,
    };
  };

  const saveProfile = async (patch: ProfilePatch, useDefault = false) => {
    const submission: FormatChoiceSubmission = {
      fingerprint: fingerprint.current,
      revision: { ...formatChoiceRevision.current },
      targetRevision: profileTargetRevision.current,
      submitted: {
        json: patch.generation_allow_json_mode_fallback !== undefined,
        prompt: patch.generation_allow_prompt_only_fallback !== undefined,
      },
      submittedProfile: generationProfile(
        patch.generation_provider,
        patch.generation_model,
        patch.generation_local_endpoint,
      ),
      baselineProfile: generationProfile(
        props.settingsResponse.generation_provider,
        props.settingsResponse.generation_model,
        props.settingsResponse.generation_local_endpoint,
      ),
      useDefault,
      baseline: props.settingsResponse,
    };
    setPendingFormatSave(submission);
    try {
      const response = await props.onSave(patch);
      if (useDefault) {
        setProvider("");
        setModel("");
        setEndpoint("");
      }
      acknowledgeFormatChoices(submission, response);
    } catch {
      setPendingFormatSave(null);
    }
  };

  const handleSave = () => {
    if (!canSave) return;
    void saveProfile(patchFor(provider, model, endpoint));
  };

  /* The draft is cleared only by the server answer: a refused save keeps
     everything the player typed. */
  const handleUseDefault = () => {
    if (props.kind !== "generation") {
      void saveProfile(patchFor("", "", ""), true);
      return;
    }
    void saveProfile(
      {
        generation_provider: null,
        generation_model: null,
        generation_local_endpoint: null,
      },
      true,
    );
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
            if (props.kind === "generation" && next !== provider) clearFormatChoices();
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
          onChange={(e) => {
            if (props.kind === "generation" && e.target.value !== model) clearFormatChoices();
            setModel(e.target.value);
          }}
        />
      </Field>

      {isLocal ? (
        <Field label={t("settings.ai.local_endpoint")} htmlFor={`${props.kind}-endpoint`}>
          <SelectInput
            id={`${props.kind}-endpoint`}
            value={endpoint}
            onChange={(e) => {
              if (props.kind === "generation" && e.target.value !== endpoint) clearFormatChoices();
              setEndpoint(e.target.value);
            }}
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

      {props.kind === "generation" ? (
        <div className="mb-2">
          <label className="flex items-start gap-2 font-display text-[11px]">
            <input
              type="checkbox"
              aria-label={t("settings.ai.json_fallback")}
              checked={formatChoices.json}
              onChange={(event) => {
                formatChoiceRevision.current.json += 1;
                const checked = event.target.checked;
                setFormatChoices((current) => ({
                  ...current,
                  json: checked,
                  dirty: { ...current.dirty, json: true },
                }));
              }}
            />
            <span>
              {t("settings.ai.json_fallback")}
              <span className="block" style={{ color: "var(--ink-faded)" }}>
                {t("settings.ai.json_fallback_hint")}
              </span>
            </span>
          </label>
          <label className="mt-2 flex items-start gap-2 font-display text-[11px]">
            <input
              type="checkbox"
              aria-label={t("settings.ai.prompt_fallback")}
              checked={formatChoices.prompt}
              onChange={(event) => {
                formatChoiceRevision.current.prompt += 1;
                const checked = event.target.checked;
                setFormatChoices((current) => ({
                  ...current,
                  prompt: checked,
                  dirty: { ...current.dirty, prompt: true },
                }));
              }}
            />
            <span>
              {t("settings.ai.prompt_fallback")}
              <span className="block" style={{ color: "var(--ink-faded)" }}>
                {t("settings.ai.prompt_fallback_hint")}
              </span>
            </span>
          </label>
        </div>
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
