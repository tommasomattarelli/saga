import { useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useUIStore } from "../../../shared/stores/ui-store";
import { getCampaignMap } from "../../../shared/api/client";
import type { MapData } from "../../../shared/api/client";
import { MapCanvas } from "./map-canvas";

/* Read-only world map (ADR 0008 B4) — parchment + pins, per-level drill-down. */
export default function WorldMap({ campaignId }: { campaignId: string }) {
  const { t } = useTranslation();
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);
  const open = sidePanel === "map";

  const { data, isLoading, error } = useQuery({
    queryKey: ["campaign-map", campaignId],
    queryFn: () => getCampaignMap(campaignId).then((r) => r.data),
    enabled: open,
  });

  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && setSidePanel(null)}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                className="fixed inset-0 z-40 bg-black/60"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              />
            </Dialog.Overlay>

            <Dialog.Content asChild>
              <motion.div
                className="fixed inset-4 z-50 flex items-center justify-center"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                <div
                  className="relative flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl"
                  style={{
                    background: "var(--parchment-base)",
                    border: "1px solid var(--line-strong)",
                  }}
                >
                  <Dialog.Title
                    className="px-6 pt-5 pb-3 font-display text-base font-semibold"
                    style={{ color: "var(--ink-primary)", borderBottom: "1px solid var(--line)" }}
                  >
                    {t("game.map")}
                  </Dialog.Title>
                  <Dialog.Close
                    aria-label={t("map.close")}
                    className="absolute top-4 right-5 z-10 text-base leading-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                    style={{ color: "var(--ink-faded)" }}
                  >
                    ✕
                  </Dialog.Close>

                  <div className="flex-1 overflow-hidden">
                    {isLoading && (
                      <p className="p-6 font-display text-sm" style={{ color: "var(--ink-faded)" }}>
                        {t("map.loading")}
                      </p>
                    )}
                    {!!error && (
                      <p className="p-6 font-display text-sm" style={{ color: "var(--blood)" }}>
                        {t("map.empty")}
                      </p>
                    )}
                    {data && <MapBody data={data} />}
                  </div>
                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}

/* Focus = the container whose outdoor children are drawn. Starts at the level
   holding the player; the breadcrumb climbs back toward the world root. */
function initialFocus(data: MapData): string {
  let cursor = data.player_position ?? data.root;
  while (cursor && data.nodes[cursor] && data.nodes[cursor].scale === "interior") {
    cursor = data.nodes[cursor].parent ?? data.root;
  }
  const parent = data.nodes[cursor]?.parent;
  return parent ?? data.root;
}

function MapBody({ data }: { data: MapData }) {
  const { t } = useTranslation();
  const [focus, setFocus] = useState<string>(() => initialFocus(data));

  const crumbs = useMemo(() => {
    const chain: string[] = [];
    let cursor: string | null = focus;
    while (cursor) {
      chain.unshift(cursor);
      cursor = data.nodes[cursor]?.parent ?? null;
    }
    return chain;
  }, [focus, data]);

  return (
    <div className="flex h-full flex-col">
      <nav
        aria-label={t("map.breadcrumb")}
        className="flex flex-wrap items-center gap-1 px-6 py-2 font-display text-xs"
        style={{ color: "var(--ink-faded)", borderBottom: "1px solid var(--line)" }}
      >
        {crumbs.map((id, i) => (
          <span key={id} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden="true">›</span>}
            <button
              onClick={() => setFocus(id)}
              className="focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              style={{
                color: id === focus ? "var(--ink-primary)" : "var(--ink-faded)",
                fontWeight: id === focus ? 600 : 400,
              }}
            >
              {data.nodes[id]?.name}
            </button>
          </span>
        ))}
      </nav>

      <div className="min-h-0 flex-1">
        <MapCanvas data={data} focus={focus} onDrillDown={setFocus} />
      </div>

      <p
        className="px-6 py-2 font-display text-[11px]"
        style={{ color: "var(--ink-faded)", borderTop: "1px solid var(--line)" }}
      >
        {t("map.hint")}
      </p>
    </div>
  );
}
