import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { getCampaigns } from "../../../shared/api/client";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { useDeleteCampaign } from "../hooks/use-delete-campaign";
import type { Campaign } from "../../../shared/types";
import { ConfirmModal } from "../../../shared/ui/modal";
import { Wordmark } from "../../../shared/ui/wordmark";

/* Campaign card — monogram now, cover image slot later (ADR 0013 A4) */
function CampaignCard({
  campaign,
  onOpen,
  onDelete,
}: {
  campaign: Campaign;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const archetype = campaign.character_data?.archetype ?? "adventurer";
  const heroName = campaign.character_data?.name ?? "Unknown hero";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="group relative w-[210px] rounded-xl p-5 text-left"
      style={{
        background: "var(--parchment-base)",
        border: "1px solid var(--line-strong)",
      }}
    >
      <button
        onClick={onOpen}
        aria-label={`Open ${campaign.name}`}
        className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
      />

      <div
        aria-hidden="true"
        className="mb-4 flex h-11 w-11 items-center justify-center rounded-lg font-display text-xl font-semibold"
        style={{ border: "1px solid var(--line-strong)", color: "var(--accent)" }}
      >
        {campaign.name[0]?.toUpperCase()}
      </div>

      <div
        className="font-display text-[15px] font-semibold"
        style={{ color: "var(--ink-primary)" }}
      >
        {campaign.name}
      </div>
      <div className="mt-0.5 mb-4 font-display text-xs" style={{ color: "var(--ink-faded)" }}>
        {heroName} · {archetype} · {campaign.death_mode}
      </div>

      <div
        className="flex items-baseline justify-between border-t pt-2.5 font-display text-xs"
        style={{ borderColor: "var(--line)", color: "var(--ink-faded)" }}
      >
        <span>{t("game.chapter")}</span>
        <span className="font-semibold" style={{ color: "var(--ink-secondary)" }}>
          {campaign.turn_number}
        </span>
      </div>

      {/* Options — on hover/focus */}
      <div
        className="absolute top-3 right-3 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="presentation"
      >
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            aria-label="Campaign options"
            className="flex h-6 w-6 items-center justify-center rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--ink-faded)" }}
          >
            ⋯
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={4}
              align="end"
              className="z-50 min-w-[140px] rounded-lg py-1 shadow-xl"
              style={{
                background: "var(--parchment-aged)",
                border: "1px solid var(--line-strong)",
              }}
            >
              <DropdownMenu.Item
                onSelect={onOpen}
                className="cursor-pointer px-3 py-1.5 font-display text-sm outline-none data-[highlighted]:bg-black/20"
                style={{ color: "var(--ink-primary)" }}
              >
                {t("campaign.open")}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={onDelete}
                className="cursor-pointer px-3 py-1.5 font-display text-sm outline-none data-[highlighted]:bg-black/20"
                style={{ color: "var(--blood)" }}
              >
                {t("campaign.delete")}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </motion.div>
  );
}

export default function CampaignSelect() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const deleteMutation = useDeleteCampaign();
  const [toDelete, setToDelete] = useState<Campaign | null>(null);

  const { data: campaigns, isLoading } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => getCampaigns().then((r) => r.data),
  });

  const handleConfirmDelete = () => {
    if (!toDelete) return;
    deleteMutation.mutate(toDelete.id, {
      onSettled: () => setToDelete(null),
    });
  };

  return (
    <div
      className="min-h-screen w-full px-8 py-10"
      style={{ background: "var(--parchment-shadow)" }}
    >
      {/* Header */}
      <header className="mx-auto mb-10 flex max-w-5xl items-center justify-between">
        <div className="flex items-baseline gap-4">
          <Wordmark size="text-lg" />
          <span className="font-display text-sm" style={{ color: "var(--ink-faded)" }}>
            {t("campaign.your_campaigns", { name: user?.username })}
          </span>
        </div>
        <button
          onClick={() => {
            logout();
            navigate("/login");
          }}
          className="font-display text-sm px-2 py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--ink-faded)" }}
        >
          {t("auth.logout")}
        </button>
      </header>

      {/* Grid */}
      <main className="mx-auto max-w-5xl">
        {isLoading ? (
          <p className="py-16 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
            {t("campaign.loading")}
          </p>
        ) : (
          <div className="flex flex-wrap gap-5">
            {campaigns?.map((c) => (
              <CampaignCard
                key={c.id}
                campaign={c}
                onOpen={() => navigate(`/game/${c.id}`)}
                onDelete={() => setToDelete(c)}
              />
            ))}

            {/* New campaign */}
            <motion.button
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => navigate("/campaigns/new")}
              aria-label={t("campaign.new_card")}
              className="flex min-h-[180px] w-[210px] items-center justify-center rounded-xl font-display text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              style={{
                border: "1px dashed var(--line-strong)",
                color: "var(--ink-faded)",
              }}
            >
              + {t("campaign.new_card")}
            </motion.button>
          </div>
        )}
      </main>

      {/* Confirm delete modal */}
      <ConfirmModal
        open={!!toDelete}
        onClose={() => setToDelete(null)}
        onConfirm={handleConfirmDelete}
        title={t("campaign.delete_title")}
        description={toDelete ? t("campaign.delete_body", { name: toDelete.name }) : ""}
        confirmLabel={t("campaign.delete")}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
}
