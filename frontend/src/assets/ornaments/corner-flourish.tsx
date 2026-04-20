/* Corner flourish SVG — 4 rotations (tl/tr/bl/br) */

type Corner = "tl" | "tr" | "bl" | "br";

const ROTATION: Record<Corner, number> = { tl: 0, tr: 90, br: 180, bl: 270 };

interface CornerFlourishProps {
  corner: Corner;
  size?: number;
  color?: string;
  className?: string;
}

export function CornerFlourish({
  corner,
  size = 32,
  color = "var(--gold-deep)",
  className,
}: CornerFlourishProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={className}
      style={{ transform: `rotate(${ROTATION[corner]}deg)` }}
    >
      {/* Main corner curve */}
      <path
        d="M2 2 Q2 16 16 16"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
      {/* Inner flourish */}
      <path
        d="M2 2 Q6 2 6 6 Q6 10 10 10"
        stroke={color}
        strokeWidth="0.8"
        strokeLinecap="round"
        fill="none"
        opacity="0.6"
      />
      {/* Terminal leaf */}
      <path
        d="M16 16 Q18 14 20 16 Q18 18 16 16 Z"
        stroke={color}
        strokeWidth="0.8"
        fill={color}
        opacity="0.7"
      />
      {/* Side tendrils */}
      <path
        d="M2 8 Q4 7 5 9"
        stroke={color}
        strokeWidth="0.7"
        strokeLinecap="round"
        fill="none"
        opacity="0.5"
      />
      <path
        d="M8 2 Q7 4 9 5"
        stroke={color}
        strokeWidth="0.7"
        strokeLinecap="round"
        fill="none"
        opacity="0.5"
      />
      {/* Corner dot */}
      <circle cx="2" cy="2" r="1.2" fill={color} opacity="0.8" />
    </svg>
  );
}
