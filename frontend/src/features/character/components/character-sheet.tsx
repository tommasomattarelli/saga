import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "../../../shared/stores/game-store";
import { useUIStore } from "../../../shared/stores/ui-store";
import { CornerFlourish } from "../../../assets/ornaments/corner-flourish";
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
                transition={{ duration: 0.3 }}
              />
            </Dialog.Overlay>

            <Dialog.Content asChild>
              <motion.div
                className="fixed inset-4 z-50 flex items-center justify-center"
                style={{ perspective: 2000 }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <motion.div
                  className="relative w-full max-w-5xl max-h-[90vh] overflow-hidden"
                  style={{
                    background: "var(--parchment-base)",
                    border: "1px solid var(--gold-deep)",
                    outline: "1px solid rgba(184, 134, 11, 0.2)",
                    outlineOffset: "4px",
                  }}
                  initial={{ rotateY: 90, opacity: 0 }}
                  animate={{ rotateY: 0, opacity: 1 }}
                  exit={{ rotateY: -90, opacity: 0 }}
                  transition={{ duration: 0.7, ease: [0.77, 0, 0.175, 1] }}
                >
                  {/* Corner flourishes */}
                  <span className="absolute top-0 left-0 -translate-x-1 -translate-y-1 pointer-events-none">
                    <CornerFlourish corner="tl" size={28} />
                  </span>
                  <span className="absolute top-0 right-0 translate-x-1 -translate-y-1 pointer-events-none">
                    <CornerFlourish corner="tr" size={28} />
                  </span>
                  <span className="absolute bottom-0 left-0 -translate-x-1 translate-y-1 pointer-events-none">
                    <CornerFlourish corner="bl" size={28} />
                  </span>
                  <span className="absolute bottom-0 right-0 translate-x-1 translate-y-1 pointer-events-none">
                    <CornerFlourish corner="br" size={28} />
                  </span>

                  {/* Close */}
                  <Dialog.Close
                    aria-label="Close character sheet"
                    className="absolute top-4 right-4 z-10 font-display text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
                    style={{ color: "var(--gold-deep)" }}
                  >
                    ✕
                  </Dialog.Close>

                  <div className="overflow-y-auto max-h-[90vh] p-8">
                    <CharacterSheetBody char={campaign.character_data} />
                  </div>
                </motion.div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
