/* Circular seal SVG — hash-stable glyph from a string seed */

interface SealProps {
  seed: string;
  size?: number;
  className?: string;
}

/* Stable hue from seed string — same seed always returns same color */
function seedToHue(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) & 0xffffff;
  }
  return h % 360;
}

/* Pick one of 6 inner glyph patterns stable from seed */
function seedToPattern(seed: string): number {
  let v = 0;
  for (let i = 0; i < seed.length; i++) v += seed.charCodeAt(i);
  return v % 6;
}

const INNER_GLYPHS = ["✦", "❖", "⚔", "◈", "⦿", "✷"];

export function Seal({ seed, size = 40, className }: SealProps) {
  const hue = seedToHue(seed);
  const glyph = INNER_GLYPHS[seedToPattern(seed)];
  const color = `hsl(${hue}, 60%, 50%)`;

  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className={className}>
      {/* Outer ring */}
      <circle
        cx="20"
        cy="20"
        r="18"
        stroke="var(--gold-deep)"
        strokeWidth="1"
        fill="none"
        opacity="0.6"
      />
      {/* Inner ring */}
      <circle cx="20" cy="20" r="14" stroke={color} strokeWidth="0.5" fill="none" opacity="0.4" />
      {/* Glyph */}
      <text
        x="20"
        y="25"
        textAnchor="middle"
        fontSize="12"
        fill={color}
        opacity="0.85"
        fontFamily="serif"
      >
        {glyph}
      </text>
    </svg>
  );
}

/* Simple initial seal — used for character portraits, player action */
interface InitialSealProps {
  name: string;
  size?: number;
  className?: string;
}

export function InitialSeal({ name, size = 40, className }: InitialSealProps) {
  const hue = seedToHue(name);
  const color = `hsl(${hue}, 55%, 45%)`;
  const initial = (name[0] ?? "?").toUpperCase();

  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" className={className}>
      <circle
        cx="20"
        cy="20"
        r="18"
        stroke="var(--gold-deep)"
        strokeWidth="1"
        fill="none"
        opacity="0.5"
      />
      <text
        x="20"
        y="25"
        textAnchor="middle"
        fontSize="16"
        fill={color}
        fontFamily="var(--font-display)"
        fontWeight="700"
      >
        {initial}
      </text>
    </svg>
  );
}
