import { forwardRef } from "react";

/* Label in Cinzel small-caps, dorato tenue */
interface AuthLabelProps {
  htmlFor: string;
  children: React.ReactNode;
}

function AuthLabel({ htmlFor, children }: AuthLabelProps) {
  return (
    <label
      htmlFor={htmlFor}
      className="font-display text-[10px] uppercase block mb-1"
      style={{
        letterSpacing: "0.22em",
        color: "var(--gold-deep)",
        fontWeight: 600,
      }}
    >
      {children}
    </label>
  );
}

/* Input senza box — solo border-bottom dorato con underline animato al focus */
interface AuthInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const AuthInput = forwardRef<HTMLInputElement, AuthInputProps>(function AuthInput(
  { label, id, className = "", ...rest },
  ref,
) {
  return (
    <div className="group relative">
      <AuthLabel htmlFor={id!}>{label}</AuthLabel>
      <input
        ref={ref}
        id={id}
        {...rest}
        className={`w-full bg-transparent px-0 py-1.5 font-body text-base focus:outline-none ${className}`}
        style={{
          color: "var(--ink-primary)",
          borderBottom: "1px solid var(--gold-deep)",
        }}
      />
      {/* Animated gold underline on focus */}
      <span
        aria-hidden="true"
        className="absolute left-0 right-0 bottom-0 h-[2px] scale-x-0 group-focus-within:scale-x-100 origin-left transition-transform duration-700 ease-out"
        style={{ background: "var(--gold-bright)" }}
      />
    </div>
  );
});

/* Ornate CTA button — bordo doppio dorato, testo Cinzel uppercase */
interface OrnateButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
}

export function OrnateButton({
  children,
  variant = "primary",
  className = "",
  ...rest
}: OrnateButtonProps) {
  const baseStyle: React.CSSProperties =
    variant === "primary"
      ? {
          background: "var(--parchment-base)",
          color: "var(--gold-bright)",
          border: "1px solid var(--gold-bright)",
          outline: "1px solid var(--gold-deep)",
          outlineOffset: "3px",
        }
      : {
          background: "transparent",
          color: "var(--gold-deep)",
          border: "1px solid var(--gold-deep)",
        };

  return (
    <button
      {...rest}
      className={`relative font-display uppercase text-xs px-6 py-3 disabled:opacity-50 transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright focus-visible:ring-offset-2 ${className}`}
      style={{
        ...baseStyle,
        letterSpacing: "0.3em",
      }}
    >
      <span className="relative z-10">{children}</span>
    </button>
  );
}

/* Inline error — Cormorant italic blood, icon-like bullet */
interface AuthErrorProps {
  message: string;
}

export function AuthError({ message }: AuthErrorProps) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="font-body italic text-sm flex items-start gap-2"
      style={{ color: "var(--blood)" }}
    >
      <span aria-hidden="true" style={{ color: "var(--blood-dark)" }}>
        ❧
      </span>
      <span>{message}</span>
    </div>
  );
}
