import {
  FlourishA,
  FlourishB,
  FlourishC,
  FlourishD,
} from "../../assets/ornaments/flourish-dividers";

type FlourishVariant = "flourish-a" | "flourish-b" | "flourish-c" | "flourish-d";

interface OrnamentDividerProps {
  variant?: FlourishVariant;
  color?: string;
  className?: string;
}

const COMPONENTS = {
  "flourish-a": FlourishA,
  "flourish-b": FlourishB,
  "flourish-c": FlourishC,
  "flourish-d": FlourishD,
} as const;

export function OrnamentDivider({
  variant = "flourish-a",
  color,
  className = "",
}: OrnamentDividerProps) {
  const Flourish = COMPONENTS[variant];
  return (
    <div
      role="separator"
      aria-hidden="true"
      className={`flex items-center justify-center my-4 ${className}`}
    >
      <Flourish color={color} />
    </div>
  );
}
