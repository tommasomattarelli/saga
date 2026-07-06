import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { CharacterSheetBody } from "./character-sheet-parts";

export default function CharacterSheet() {
  const campaign = useGameStore((s) => s.campaign);
  const sidePanel = useUIStore((s) => s.sidePanel);
  const setSidePanel = useUIStore((s) => s.setSidePanel);

  const open = sidePanel === "character";

  if (!campaign) return null;

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
                  className="relative flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl"
                  style={{
                    background: "var(--parchment-base)",
                    border: "1px solid var(--line-strong)",
                  }}
                >
                  <Dialog.Close
                    aria-label="Close character sheet"
                    className="absolute top-4 right-5 z-10 text-base leading-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
                    style={{ color: "var(--ink-faded)" }}
                  >
                    ✕
                  </Dialog.Close>

                  <CharacterSheetBody char={campaign.character_data} />
                </div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
