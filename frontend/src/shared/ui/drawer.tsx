import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** Width class, defaults to w-[480px] */
  width?: string;
}

export function Drawer({ open, onClose, title, children, width = "w-[480px]" }: DrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            {/* Overlay */}
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="fixed inset-0 z-40 bg-black/50"
                aria-hidden="true"
              />
            </Dialog.Overlay>

            {/* Panel */}
            <Dialog.Content asChild>
              <motion.div
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ duration: 0.4, ease: [0.77, 0, 0.175, 1] }}
                className={`fixed right-0 top-0 bottom-0 z-50 ${width} flex flex-col`}
                style={{
                  background: "var(--parchment-aged)",
                  borderLeft: "1px solid var(--gold-deep)",
                }}
              >
                {/* Header */}
                <div
                  className="flex items-center justify-between px-6 py-4 shrink-0"
                  style={{ borderBottom: "1px solid var(--gold-deep)", opacity: 0.9 }}
                >
                  <Dialog.Title
                    className="font-display text-xl tracking-grimoire uppercase"
                    style={{ color: "var(--gold-bright)" }}
                  >
                    {title}
                  </Dialog.Title>
                  <Dialog.Close
                    aria-label="Close drawer"
                    className="text-xl leading-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright focus-visible:ring-offset-2"
                    style={{ color: "var(--gold-deep)" }}
                  >
                    ✕
                  </Dialog.Close>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto px-6 py-4">{children}</div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
