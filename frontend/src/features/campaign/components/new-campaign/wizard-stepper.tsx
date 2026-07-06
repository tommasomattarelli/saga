import { useTranslation } from "react-i18next";

interface WizardStepperProps {
  step: 1 | 2 | 3;
}

export function WizardStepper({ step }: WizardStepperProps) {
  const { t } = useTranslation();
  const labels = [t("wizard.step_world"), t("wizard.step_hero"), t("wizard.step_fate")];

  return (
    <div className="mb-8 flex items-center justify-center gap-3" aria-label={`Step ${step} of 3`}>
      {labels.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3;
        const isActive = n === step;
        const isDone = n < step;
        return (
          <div key={label} className="flex items-center gap-3">
            <div className="flex items-center gap-2" aria-current={isActive ? "step" : undefined}>
              <span
                className="flex h-6 w-6 items-center justify-center rounded-full font-display text-xs font-semibold"
                style={{
                  border: `1px solid ${isActive || isDone ? "var(--accent)" : "var(--line-strong)"}`,
                  color: isActive || isDone ? "var(--accent)" : "var(--ink-faded)",
                }}
              >
                {n}
              </span>
              <span
                className="font-display text-[13px]"
                style={{ color: isActive ? "var(--ink-primary)" : "var(--ink-faded)" }}
              >
                {label}
              </span>
            </div>
            {i < labels.length - 1 && (
              <span
                aria-hidden="true"
                className="h-px w-10"
                style={{ background: isDone ? "var(--accent)" : "var(--line)" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
