/* Shared boxed inputs for the world editor — same visual language as the auth card. */

interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function Field({ label, id, className = "", ...rest }: FieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="font-display text-xs block mb-1.5"
        style={{ color: "var(--ink-secondary)" }}
      >
        {label}
      </label>
      <input
        id={id}
        {...rest}
        className={`w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent ${className}`}
        style={{
          color: "var(--ink-primary)",
          background: "var(--parchment-aged)",
          border: "1px solid var(--line-strong)",
        }}
      />
    </div>
  );
}

interface AreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
}

export function Area({ label, id, className = "", ...rest }: AreaProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="font-display text-xs block mb-1.5"
        style={{ color: "var(--ink-secondary)" }}
      >
        {label}
      </label>
      <textarea
        id={id}
        rows={4}
        {...rest}
        className={`w-full rounded-lg px-3 py-2 font-body text-sm focus:outline-none focus:ring-1 focus:ring-accent ${className}`}
        style={{
          color: "var(--ink-primary)",
          background: "var(--parchment-aged)",
          border: "1px solid var(--line-strong)",
        }}
      />
    </div>
  );
}

interface PickerProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: { value: string; label: string }[];
  allowEmpty?: boolean;
}

/* References are picked, never typed (ADR 0008 I4 — broken refs prevented by construction) */
export function Picker({ label, id, options, allowEmpty, className = "", ...rest }: PickerProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="font-display text-xs block mb-1.5"
        style={{ color: "var(--ink-secondary)" }}
      >
        {label}
      </label>
      <select
        id={id}
        {...rest}
        className={`w-full rounded-lg px-3 py-2 font-display text-sm focus:outline-none focus:ring-1 focus:ring-accent ${className}`}
        style={{
          color: "var(--ink-primary)",
          background: "var(--parchment-aged)",
          border: "1px solid var(--line-strong)",
        }}
      >
        {allowEmpty && <option value="">—</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function GhostButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-lg px-3 py-1.5 font-display text-xs disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent ${className}`}
      style={{ color: "var(--ink-secondary)", border: "1px solid var(--line-strong)" }}
    >
      {children}
    </button>
  );
}

export function PrimaryButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-lg px-5 py-2 font-display text-sm font-semibold disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent ${className}`}
      style={{
        color: "var(--accent)",
        border: "1px solid var(--accent)",
        background: "transparent",
      }}
    >
      {children}
    </button>
  );
}
