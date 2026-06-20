import { Seal } from "./seal";

/* Book spine SVG — verticale, colore derivato dalla classe, sigillo da campaign.id */

const CLASS_SPINE_COLORS: Record<string, { base: string; accent: string }> = {
  warrior: { base: "#5C1410", accent: "#8B0000" },
  rogue: { base: "#2D1F3D", accent: "#5C3D78" },
  mage: { base: "#152438", accent: "#2D4A78" },
  ranger: { base: "#1F3020", accent: "#3D5C3D" },
  cleric: { base: "#3D2810", accent: "#8B6914" },
  bard: { base: "#3D1628", accent: "#5C1A3D" },
  default: { base: "#2A1A10", accent: "#5A4530" },
};

interface BookSpineProps {
  campaignId: string;
  title: string;
  archetype: string;
  turnNumber: number;
  ironman?: boolean;
  width?: number;
  height?: number;
  className?: string;
}

export function BookSpine({
  campaignId,
  title,
  archetype,
  turnNumber,
  ironman = false,
  width = 80,
  height = 260,
  className,
}: BookSpineProps) {
  const palette = CLASS_SPINE_COLORS[archetype] ?? CLASS_SPINE_COLORS["default"];
  // HP-like ring progress: turn_number / 100, clamped — used as "experience fill"
  const progress = Math.min(1, turnNumber / 100);

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 80 260"
      aria-label={title}
      className={className}
    >
      <defs>
        <linearGradient id={`spine-grad-${campaignId}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={palette.base} stopOpacity="1" />
          <stop offset="50%" stopColor={palette.accent} stopOpacity="1" />
          <stop offset="100%" stopColor={palette.base} stopOpacity="1" />
        </linearGradient>
        {/* Subtle leather texture */}
        <pattern
          id={`leather-${campaignId}`}
          x="0"
          y="0"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
        >
          <rect width="6" height="6" fill={palette.base} opacity="0" />
          <circle cx="3" cy="3" r="0.4" fill="#000" opacity="0.15" />
        </pattern>
      </defs>

      {/* Main spine */}
      <rect
        x="4"
        y="6"
        width="72"
        height="248"
        rx="2"
        fill={`url(#spine-grad-${campaignId})`}
        stroke="var(--gold-deep)"
        strokeWidth="0.8"
      />
      <rect x="4" y="6" width="72" height="248" rx="2" fill={`url(#leather-${campaignId})`} />

      {/* Horizontal gold rules */}
      {[24, 96, 164, 236].map((y) => (
        <line
          key={y}
          x1="10"
          y1={y}
          x2="70"
          y2={y}
          stroke="var(--gold-deep)"
          strokeWidth="0.6"
          opacity="0.7"
        />
      ))}

      {/* Upper cartouche with central seal */}
      <g transform="translate(40, 50)">
        <Seal seed={campaignId} size={44} />
      </g>

      {/* Ironman wax seal (top) */}
      {ironman && (
        <g transform="translate(40, 16)">
          <circle cx="0" cy="0" r="6" fill="#8B0000" stroke="#5A0A0A" strokeWidth="0.5" />
          <path
            d="M -2 -2 L 2 2 M -2 2 L 2 -2"
            stroke="#5A0A0A"
            strokeWidth="0.6"
            strokeLinecap="round"
          />
        </g>
      )}

      {/* Title — rotated 90° in central section */}
      <g transform="translate(40, 170) rotate(90)">
        <text
          x="0"
          y="4"
          textAnchor="middle"
          fontSize="11"
          fill="var(--gold-bright)"
          fontFamily="var(--font-display)"
          letterSpacing="0.15em"
          style={{
            textTransform: "uppercase",
          }}
        >
          {title.length > 18 ? `${title.slice(0, 17)}…` : title}
        </text>
      </g>

      {/* Bottom HP ring (progress indicator = turn number / 100) */}
      <g transform="translate(40, 230)">
        <circle
          cx="0"
          cy="0"
          r="10"
          fill="none"
          stroke="var(--gold-deep)"
          strokeWidth="1"
          opacity="0.5"
        />
        <circle
          cx="0"
          cy="0"
          r="10"
          fill="none"
          stroke="var(--gold-bright)"
          strokeWidth="1.5"
          strokeDasharray={`${progress * 62.8} 62.8`}
          transform="rotate(-90)"
        />
        <text
          x="0"
          y="3"
          textAnchor="middle"
          fontSize="7"
          fill="var(--gold-bright)"
          fontFamily="var(--font-display)"
        >
          {turnNumber}
        </text>
      </g>
    </svg>
  );
}

/* Empty placeholder book for "Begin New Saga" — white virgin cover with + */
interface NewBookSpineProps {
  width?: number;
  height?: number;
  className?: string;
}

export function NewBookSpine({ width = 80, height = 260, className }: NewBookSpineProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 80 260"
      aria-hidden="true"
      className={className}
    >
      <rect
        x="4"
        y="6"
        width="72"
        height="248"
        rx="2"
        fill="var(--parchment-base)"
        stroke="var(--gold-deep)"
        strokeWidth="0.8"
        strokeDasharray="3 3"
        opacity="0.45"
      />
      <text
        x="40"
        y="140"
        textAnchor="middle"
        fontSize="36"
        fill="var(--gold-bright)"
        fontFamily="var(--font-display)"
        fontWeight="300"
      >
        +
      </text>
    </svg>
  );
}
