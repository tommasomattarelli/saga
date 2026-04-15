import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCampaigns } from "../../../shared/api/client";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { useDeleteCampaign } from "../hooks/use-delete-campaign";
import type { Campaign } from "../../../shared/types";

function CampaignCard({
  campaign,
  onDelete,
  isDeleting,
}: {
  campaign: Campaign;
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="relative rounded-lg border border-parchment-700/30 bg-parchment-900/60 transition hover:border-gold-500/50 hover:bg-parchment-800/60">
      <button
        onClick={() => navigate(`/game/${campaign.id}`)}
        className="w-full p-4 text-left"
      >
        <h3 className="font-display text-lg text-gold-400">{campaign.name}</h3>
        <div className="mt-1 flex gap-3 text-sm text-parchment-400">
          <span>Turn {campaign.turn_number}</span>
          <span className="capitalize">{campaign.death_mode}</span>
          <span className="capitalize">{campaign.status}</span>
        </div>
        <p className="mt-2 text-xs text-parchment-500">
          {campaign.character_data?.name || "Unknown hero"} &mdash; {campaign.template_id}
        </p>
      </button>

      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          aria-label={`Delete ${campaign.name}`}
          className="absolute right-3 top-3 rounded px-2 py-1 text-xs text-parchment-600 hover:bg-parchment-800 hover:text-red-400"
        >
          Delete
        </button>
      ) : (
        <div className="absolute right-3 top-3 flex items-center gap-2 rounded bg-parchment-800 px-2 py-1">
          <span className="text-xs text-parchment-300">Are you sure?</span>
          <button
            onClick={() => {
              onDelete(campaign.id);
              setConfirming(false);
            }}
            disabled={isDeleting}
            className="text-xs font-semibold text-red-400 hover:text-red-300 disabled:opacity-50"
          >
            Delete
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="text-xs text-parchment-500 hover:text-parchment-300"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

export default function CampaignSelect() {
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const deleteMutation = useDeleteCampaign();

  const { data: campaigns, isLoading } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => getCampaigns().then((r) => r.data),
  });

  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold text-gold-400">Your Sagas</h1>
          <p className="text-sm text-parchment-400">Welcome back, {user?.username}</p>
        </div>
        <button
          onClick={() => {
            logout();
            navigate("/login");
          }}
          className="text-sm text-parchment-500 hover:text-parchment-300"
        >
          Sign out
        </button>
      </div>

      {isLoading ? (
        <p className="text-parchment-400">Loading campaigns...</p>
      ) : (
        <div className="space-y-3">
          {campaigns?.map((c) => (
            <CampaignCard
              key={c.id}
              campaign={c}
              onDelete={(id) => deleteMutation.mutate(id)}
              isDeleting={deleteMutation.isPending}
            />
          ))}
          {(!campaigns || campaigns.length === 0) && (
            <p className="text-parchment-500">No campaigns yet. Start a new adventure!</p>
          )}
        </div>
      )}

      <button
        onClick={() => navigate("/campaigns/new")}
        className="mt-6 w-full rounded-lg border-2 border-dashed border-gold-500/30 py-4 text-gold-400 transition hover:border-gold-500/60 hover:bg-parchment-800/30"
      >
        + Begin a New Saga
      </button>
    </div>
  );
}
