import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getWorld, saveWorld } from "../../../shared/api/client";
import type { EditableWorld } from "../../../shared/api/client";
import { EditorNav } from "./editor-nav";
import type { Selection } from "./editor-nav";
import { MetaForm, ScenarioForm, TaxonomyForm } from "./forms-world";
import { NodeForm } from "./forms-node";
import { CollectionForm } from "./forms-collections";
import { PrimaryButton } from "./editor-inputs";

/* Per-entity world editor (ADR 0008 I6/I7): edit → validate server-side → git commit. */
export default function WorldEditor() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [payload, setPayload] = useState<EditableWorld | null>(null);
  const [selection, setSelection] = useState<Selection>({ type: "meta" });
  const [dirty, setDirty] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  const { isLoading, error } = useQuery({
    queryKey: ["world-edit", slug],
    queryFn: () =>
      getWorld(slug!).then((r) => {
        setPayload(r.data);
        return r.data;
      }),
    enabled: !!slug && payload === null,
  });

  const saveMutation = useMutation({
    mutationFn: () => saveWorld(slug!, payload!).then((r) => r.data),
    onSuccess: () => {
      setDirty(false);
      setErrors([]);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
        ?.detail;
      if (typeof detail === "string") setErrors([detail]);
      else if (detail && typeof detail === "object") {
        const d = detail as { message?: string; errors?: string[] };
        setErrors([d.message ?? t("worlds.save_failed"), ...(d.errors ?? [])]);
      } else setErrors([t("worlds.save_failed")]);
    },
  });

  const update = (next: EditableWorld) => {
    setPayload(next);
    setDirty(true);
  };

  if (isLoading || !payload) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ background: "var(--parchment-shadow)" }}
      >
        <p className="font-display text-sm" style={{ color: "var(--ink-secondary)" }}>
          {error ? t("worlds.load_failed") : t("worlds.loading")}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col" style={{ background: "var(--parchment-shadow)" }}>
      <header
        className="flex items-center justify-between px-6 py-3"
        style={{ background: "var(--parchment-aged)", borderBottom: "1px solid var(--line)" }}
      >
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate("/worlds")}
            className="font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--ink-faded)" }}
          >
            ← {t("worlds.title")}
          </button>
          <h1
            className="font-display text-base font-semibold"
            style={{ color: "var(--ink-primary)" }}
          >
            {payload.meta.name}
          </h1>
          {dirty && (
            <span className="font-display text-xs" style={{ color: "var(--ink-faded)" }}>
              {t("worlds.unsaved")}
            </span>
          )}
          {saved && (
            <span className="font-display text-xs" style={{ color: "var(--accent)" }}>
              {t("worlds.saved")}
            </span>
          )}
        </div>
        <PrimaryButton
          disabled={!dirty || saveMutation.isPending}
          onClick={() => saveMutation.mutate()}
        >
          {saveMutation.isPending ? t("worlds.saving") : t("worlds.save")}
        </PrimaryButton>
      </header>

      {errors.length > 0 && (
        <div
          role="alert"
          className="mx-6 mt-4 rounded-lg px-4 py-3 font-display text-xs"
          style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
        >
          {errors.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <EditorNav
          payload={payload}
          selection={selection}
          onSelect={setSelection}
          onChange={update}
        />

        <main className="min-h-0 flex-1 overflow-y-auto p-6">
          <div
            className="mx-auto max-w-2xl rounded-xl p-6"
            style={{ background: "var(--parchment-base)", border: "1px solid var(--line-strong)" }}
          >
            {selection.type === "meta" && <MetaForm payload={payload} onChange={update} />}
            {selection.type === "taxonomy" && <TaxonomyForm payload={payload} onChange={update} />}
            {selection.type === "scenario" && <ScenarioForm payload={payload} onChange={update} />}
            {selection.type === "node" && (
              <NodeForm
                payload={payload}
                slug={selection.slug!}
                onChange={update}
                onSelect={setSelection}
              />
            )}
            {(selection.type === "edge" ||
              selection.type === "faction" ||
              selection.type === "npc" ||
              selection.type === "encounter") && (
              <CollectionForm
                payload={payload}
                kind={selection.type}
                slug={selection.slug!}
                onChange={update}
                onSelect={setSelection}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
