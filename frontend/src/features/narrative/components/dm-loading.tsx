import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";

export default function DmLoading() {
  const { t } = useTranslation();

  return (
    <div className="mb-6 py-6 text-center" data-testid="dm-loading">
      <div className="flex items-center justify-center gap-1.5 mb-3">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="block rounded-full"
            style={{
              width: 5,
              height: 5,
              background: "var(--ink-faded)",
            }}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.3,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
      <p className="font-display text-sm" style={{ color: "var(--ink-faded)" }}>
        {t("game.dm_writing")}
      </p>
    </div>
  );
}
