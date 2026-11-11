import { useTranslation } from "react-i18next";

interface ActionErrorBannerProps {
  actionError: string | null;
  historyError: boolean;
  memoryRetryRequired: boolean;
  onMemoryRetry: () => void;
}

export default function ActionErrorBanner({
  actionError,
  historyError,
  memoryRetryRequired,
  onMemoryRetry,
}: ActionErrorBannerProps) {
  const { t } = useTranslation();
  if (!historyError && !actionError) return null;

  return (
    <div
      role="alert"
      className="mb-6 rounded-md px-4 py-3 font-display text-sm"
      style={{ border: "1px solid var(--blood-dark)", color: "var(--blood)" }}
    >
      {actionError ?? t("game.history_error")}
      {actionError && memoryRetryRequired && (
        <button className="ml-3 underline" onClick={onMemoryRetry}>
          {t("errors.memory_retry")}
        </button>
      )}
    </div>
  );
}
