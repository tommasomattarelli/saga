import * as Dialog from "@radix-ui/react-dialog";
import { motion, AnimatePresence } from "framer-motion";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  /** When true, renders fullscreen (e.g. character sheet) */
  fullscreen?: boolean;
  /** Max width class when not fullscreen, defaults to max-w-2xl */
  maxWidth?: string;
}

function Modal({
  open,
  onClose,
  title,
  children,
  fullscreen = false,
  maxWidth = "max-w-2xl",
}: ModalProps) {
  const containerClass = fullscreen
    ? "fixed inset-4 z-50 flex flex-col rounded"
    : `fixed inset-0 z-50 flex items-center justify-center p-6`;

  const contentClass = fullscreen
    ? "w-full h-full flex flex-col"
    : `relative w-full ${maxWidth} flex flex-col rounded`;

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
                className="fixed inset-0 z-40 bg-black/60"
                aria-hidden="true"
              />
            </Dialog.Overlay>

            {/* Content */}
            <div className={containerClass}>
              <Dialog.Content asChild>
                <motion.div
                  initial={{ opacity: 0, rotateY: 90 }}
                  animate={{ opacity: 1, rotateY: 0 }}
                  exit={{ opacity: 0, rotateY: -90 }}
                  transition={{ duration: 0.7, ease: [0.77, 0, 0.175, 1] }}
                  style={{
                    perspective: 1200,
                    background: "var(--parchment-base)",
                    border: "1px solid var(--gold-deep)",
                  }}
                  className={contentClass}
                >
                  {/* Header */}
                  <div
                    className="flex items-center justify-between px-8 py-5 shrink-0"
                    style={{ borderBottom: "1px solid var(--gold-deep)" }}
                  >
                    <Dialog.Title
                      className="font-display text-2xl tracking-grimoire uppercase"
                      style={{ color: "var(--gold-bright)" }}
                    >
                      {title}
                    </Dialog.Title>
                    <Dialog.Close
                      aria-label="Close"
                      className="text-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright focus-visible:ring-offset-2"
                      style={{ color: "var(--gold-deep)" }}
                    >
                      ✕
                    </Dialog.Close>
                  </div>

                  {/* Body */}
                  <div className="flex-1 overflow-y-auto">{children}</div>
                </motion.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}

/* Confirm dialog — used for destructive actions (e.g. delete campaign) */
interface ConfirmModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  isPending?: boolean;
}

export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  isPending = false,
}: ConfirmModalProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} maxWidth="max-w-md">
      <div className="px-8 py-6 space-y-6">
        <p className="font-body text-base" style={{ color: "var(--ink-secondary)" }}>
          {description}
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={isPending}
            className="px-4 py-2 font-display text-xs tracking-grimoire uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright"
            style={{ color: "var(--ink-faded)", border: "1px solid var(--ink-faded)" }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 font-display text-xs tracking-grimoire uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blood"
            style={{
              color: "var(--blood)",
              border: "1px solid var(--blood)",
              opacity: isPending ? 0.6 : 1,
            }}
          >
            {isPending ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
