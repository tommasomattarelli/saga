import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  createWorld,
  deleteWorld,
  exportWorld,
  getWorlds,
  importWorld,
} from "../../../shared/api/client";
import type { WorldOption } from "../../../shared/api/client";
import { Field, Area, GhostButton, PrimaryButton } from "./editor-inputs";

/* World library manager (ADR 0008 C9/I7): create, edit, export, import, delete. */
export default function WorldLibrary() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", author: "", description: "" });
  const [error, setError] = useState<string | null>(null);

  const { data: worlds, isLoading } = useQuery({
    queryKey: ["worlds"],
    queryFn: () => getWorlds().then((r) => r.data),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["worlds"] });

  const createMutation = useMutation({
    mutationFn: () => createWorld(form).then((r) => r.data),
    onSuccess: (card) => {
      refresh();
      navigate(`/worlds/${card.slug}`);
    },
    onError: () => setError(t("worlds.create_failed")),
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importWorld(file).then((r) => r.data),
    onSuccess: refresh,
    onError: () => setError(t("worlds.import_failed")),
  });

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => deleteWorld(slug),
    onSuccess: refresh,
    onError: () => setError(t("worlds.delete_failed")),
  });

  const handleExport = async (slug: string) => {
    const resp = await exportWorld(slug);
    const url = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.zip`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen w-full" style={{ background: "var(--parchment-shadow)" }}>
      <div className="mx-auto max-w-[920px] px-6 py-10">
        <div className="mb-8 flex items-center justify-between">
          <button
            onClick={() => navigate("/campaigns")}
            className="font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--ink-faded)" }}
          >
            ← {t("worlds.back")}
          </button>
          <h1
            className="font-display text-base font-semibold"
            style={{ color: "var(--ink-primary)" }}
          >
            {t("worlds.title")}
          </h1>
          <div className="flex gap-2">
            <GhostButton onClick={() => fileRef.current?.click()}>{t("worlds.import")}</GhostButton>
            <GhostButton onClick={() => setCreating((v) => !v)}>{t("worlds.create")}</GhostButton>
          </div>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept=".zip"
          className="hidden"
          aria-label={t("worlds.import")}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) importMutation.mutate(file);
            e.target.value = "";
          }}
        />

        {error && (
          <div
            role="alert"
            className="mb-6 rounded-lg px-4 py-3 font-display text-sm"
            style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
          >
            {error}
          </div>
        )}

        {creating && (
          <div
            className="mb-8 space-y-4 rounded-xl p-6"
            style={{ background: "var(--parchment-base)", border: "1px solid var(--line-strong)" }}
          >
            <h2
              className="font-display text-sm font-semibold"
              style={{ color: "var(--ink-primary)" }}
            >
              {t("worlds.create_title")}
            </h2>
            <Field
              id="world-name"
              label={t("worlds.name")}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Field
              id="world-author"
              label={t("worlds.author")}
              value={form.author}
              onChange={(e) => setForm({ ...form, author: e.target.value })}
            />
            <Area
              id="world-description"
              label={t("worlds.description")}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <PrimaryButton
              disabled={!form.name.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {t("worlds.create_confirm")}
            </PrimaryButton>
          </div>
        )}

        {isLoading && (
          <p className="font-display text-sm" style={{ color: "var(--ink-faded)" }}>
            {t("worlds.loading")}
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {worlds?.map((world: WorldOption) => (
            <div
              key={world.slug}
              className="rounded-xl p-5"
              style={{
                background: "var(--parchment-base)",
                border: "1px solid var(--line-strong)",
              }}
            >
              <h3
                className="font-display text-[15px] font-semibold"
                style={{ color: "var(--ink-primary)" }}
              >
                {world.name}
              </h3>
              <p className="mt-1.5 font-body text-sm" style={{ color: "var(--ink-secondary)" }}>
                {world.description}
              </p>
              <div className="mt-3 font-display text-xs" style={{ color: "var(--ink-faded)" }}>
                {world.author && `${t("wizard.by")} ${world.author} · `}v{world.version}
              </div>
              <div className="mt-4 flex gap-2">
                <GhostButton onClick={() => navigate(`/worlds/${world.slug}`)}>
                  {t("worlds.edit")}
                </GhostButton>
                <GhostButton onClick={() => handleExport(world.slug)}>
                  {t("worlds.export")}
                </GhostButton>
                <GhostButton
                  onClick={() => {
                    if (window.confirm(t("worlds.delete_confirm", { name: world.name }))) {
                      deleteMutation.mutate(world.slug);
                    }
                  }}
                >
                  {t("worlds.delete")}
                </GhostButton>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
