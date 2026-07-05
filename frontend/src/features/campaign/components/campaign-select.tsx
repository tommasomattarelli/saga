import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import * as Tooltip from "@radix-ui/react-tooltip";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { getCampaigns } from "../../../shared/api/client";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { useDeleteCampaign } from "../hooks/use-delete-campaign";
import type { Campaign } from "../../../shared/types";
import { BookSpine, NewBookSpine } from "../../../assets/ornaments/book-spine";
import { OrnamentDivider } from "../../../shared/ui/ornament-divider";
import { ConfirmModal } from "../../../shared/ui/modal";
import { SagaSeal } from "../../../assets/ornaments/saga-seal";

function TomeCard({
  campaign,
  onOpen,
  onDelete,
}: {
  campaign: Campaign;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const archetype = campaign.character_data?.archetype ?? "default";
  const heroName = campaign.character_data?.name ?? "Unknown hero";
  const ironman = campaign.death_mode === "ironman";

  return (
    <Tooltip.Root delayDuration={300}>
      <Tooltip.Trigger asChild>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          whileHover={{ y: -10, rotate: -2 }}
          transition={{ type: "spring", stiffness: 300, damping: 22 }}
          className="relative group cursor-pointer"
          style={{ width: 80, height: 260 }}
        >
          <button
            onClick={onOpen}
            aria-label={`Open ${campaign.name}`}
            className="absolute inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright rounded"
          >
            <BookSpine
              campaignId={campaign.id}
              title={campaign.name}
              archetype={archetype}
              turnNumber={campaign.turn_number}
              ironman={ironman}
            />
          </button>

          {/* Hover glow */}
          <div
            aria-hidden="true"
            className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
            style={{
              boxShadow: "0 0 30px 4px rgba(212, 175, 55, 0.4)",
              borderRadius: "4px",
            }}
          />

          {/* Dropdown menu trigger — appears on hover */}
          <div
            className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            role="presentation"
          >
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                aria-label="Campaign options"
                className="w-6 h-6 flex items-center justify-center rounded bg-black/60 text-gold-bright focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-gold-bright"
              >
                ⋯
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  sideOffset={4}
                  align="end"
                  className="min-w-[140px] py-1 shadow-xl z-50"
                  style={{
                    background: "var(--parchment-aged)",
                    border: "1px solid var(--gold-deep)",
                  }}
                >
                  <DropdownMenu.Item
                    onSelect={onOpen}
                    className="px-3 py-1.5 font-body text-sm cursor-pointer outline-none data-[highlighted]:bg-black/10"
                    style={{ color: "var(--ink-primary)" }}
                  >
                    Open tome
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={onDelete}
                    className="px-3 py-1.5 font-body text-sm cursor-pointer outline-none data-[highlighted]:bg-black/10"
                    style={{ color: "var(--blood)" }}
                  >
                    Burn tome
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </motion.div>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          sideOffset={10}
          className="z-50 px-3 py-2 max-w-[220px] font-body text-sm shadow-lg"
          style={{
            background: "var(--parchment-aged)",
            color: "var(--ink-primary)",
            border: "1px solid var(--gold-deep)",
          }}
        >
          <div
            className="font-display text-xs uppercase tracking-grimoire"
            style={{ color: "var(--gold-bright)" }}
          >
            {campaign.name}
          </div>
          <div className="mt-1 italic" style={{ color: "var(--ink-secondary)" }}>
            {heroName} · {archetype}
          </div>
          <div className="mt-1 text-xs" style={{ color: "var(--ink-faded)" }}>
            Chapter {campaign.turn_number} · {campaign.death_mode}
          </div>
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export default function CampaignSelect() {
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
    <Tooltip.Provider>
      <div
        className="min-h-screen w-full px-8 py-12"
        style={{ background: "var(--parchment-base)" }}
      >
        {/* Header */}
        <header className="max-w-6xl mx-auto flex items-start justify-between mb-10">
          <div className="flex items-center gap-4">
            <SagaSeal size={48} color="var(--gold-bright)" animate={false} />
            <div>
              <p
                className="font-display text-[10px] uppercase"
                style={{ color: "var(--ink-faded)", letterSpacing: "0.3em" }}
              >
                Welcome, {user?.username}
              </p>
              <h1
                className="font-display text-4xl uppercase"
                style={{ color: "var(--gold-bright)", letterSpacing: "0.18em" }}
              >
                The Shelf of Tales
              </h1>
            </div>
          </div>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="font-display text-xs uppercase tracking-grimoire-wide px-4 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
            style={{ color: "var(--ink-faded)" }}
          >
            Depart
          </button>
        </header>

        <OrnamentDivider variant="flourish-a" className="max-w-5xl mx-auto" />

        {/* Shelf */}
        <main className="max-w-6xl mx-auto">
          {isLoading ? (
            <p className="text-center font-body italic py-16" style={{ color: "var(--ink-faded)" }}>
              Retrieving the tomes…
            </p>
          ) : (
            <>
              <div className="relative mt-8 flex flex-wrap items-end justify-center gap-8 pb-8">
                {campaigns?.map((c) => (
                  <TomeCard
                    key={c.id}
                    campaign={c}
                    onOpen={() => navigate(`/game/${c.id}`)}
                    onDelete={() => setToDelete(c)}
                  />
                ))}

                {/* New Saga tome */}
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  whileHover={{ y: -10, rotate: 2 }}
                  transition={{ type: "spring", stiffness: 300, damping: 22 }}
                  className="relative group cursor-pointer"
                  style={{ width: 80, height: 260 }}
                >
                  <button
                    onClick={() => navigate("/campaigns/new")}
                    aria-label="Begin a new saga"
                    className="absolute inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright rounded"
                  >
                    <NewBookSpine />
                  </button>
                  <div
                    aria-hidden="true"
                    className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                    style={{
                      boxShadow: "0 0 40px 6px rgba(212, 175, 55, 0.55)",
                      borderRadius: "4px",
                    }}
                  />
                </motion.div>
              </div>

              {/* Wooden shelf ledge */}
              <div
                aria-hidden="true"
                className="max-w-6xl mx-auto h-3"
                style={{
                  background:
                    "linear-gradient(to bottom, var(--gold-deep) 0%, rgba(0,0,0,0.4) 50%, var(--gold-deep) 100%)",
                  borderTop: "1px solid var(--gold)",
                  borderBottom: "1px solid rgba(0,0,0,0.5)",
                }}
              />
              <div
                aria-hidden="true"
                className="max-w-6xl mx-auto h-4"
                style={{
                  background: "linear-gradient(to bottom, rgba(0,0,0,0.35), rgba(0,0,0,0))",
                }}
              />

              {(!campaigns || campaigns.length === 0) && (
                <p
                  className="mt-10 text-center font-body italic text-lg"
                  style={{ color: "var(--ink-faded)" }}
                >
                  The shelf is empty. Begin thy first saga.
                </p>
              )}
            </>
          )}
        </main>

        {/* Confirm delete modal */}
        <ConfirmModal
          open={!!toDelete}
          onClose={() => setToDelete(null)}
          onConfirm={handleConfirmDelete}
          title="Burn this tome?"
          description={
            toDelete ? `"${toDelete.name}" will be lost to the ages. This cannot be undone.` : ""
          }
          confirmLabel="Burn"
          isPending={deleteMutation.isPending}
        />
      </div>
    </Tooltip.Provider>
  );
}
