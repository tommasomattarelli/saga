import { CornerFlourish } from "../../assets/ornaments/corner-flourish";

type FrameVariant = "small" | "medium" | "large";

interface OrnateFrameProps {
  children: React.ReactNode;
  variant?: FrameVariant;
  className?: string;
  /** Override the border/corner color */
  color?: string;
}

const CORNER_SIZE: Record<FrameVariant, number> = {
  small: 20,
  medium: 28,
  large: 36,
};

const PADDING: Record<FrameVariant, string> = {
  small: "p-4",
  medium: "p-6",
  large: "p-8",
};

export function OrnateFrame({
  children,
  variant = "medium",
  className = "",
  color,
}: OrnateFrameProps) {
  const cornerSize = CORNER_SIZE[variant];
  const padding = PADDING[variant];

  return (
    <div
      className={`relative ${padding} ${className}`}
      style={{
        border: "1px solid rgba(139, 105, 20, 0.6)",
        outline: "1px solid rgba(184, 134, 11, 0.2)",
        outlineOffset: "3px",
      }}
    >
      {/* Corner ornaments */}
      <span className="absolute top-0 left-0 -translate-x-1 -translate-y-1">
        <CornerFlourish corner="tl" size={cornerSize} color={color} />
      </span>
      <span className="absolute top-0 right-0 translate-x-1 -translate-y-1">
        <CornerFlourish corner="tr" size={cornerSize} color={color} />
      </span>
      <span className="absolute bottom-0 left-0 -translate-x-1 translate-y-1">
        <CornerFlourish corner="bl" size={cornerSize} color={color} />
      </span>
      <span className="absolute bottom-0 right-0 translate-x-1 translate-y-1">
        <CornerFlourish corner="br" size={cornerSize} color={color} />
      </span>

      {children}
    </div>
  );
}
