/* Ornamental flourish dividers — 4 variants (a/b/c/d) */

interface FlourishProps {
  color?: string;
  width?: number;
  height?: number;
  className?: string;
}

/* Variant A — symmetric floral vine */
export function FlourishA({
  color = "var(--gold-deep)",
  width = 280,
  height = 20,
  className,
}: FlourishProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 280 20"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      {/* Central diamond */}
      <path d="M140 4 L144 10 L140 16 L136 10 Z" fill={color} opacity="0.8" />
      {/* Left vine */}
      <path
        d="M136 10 Q110 10 80 8 Q50 6 20 10"
        stroke={color}
        strokeWidth="0.8"
        fill="none"
        opacity="0.6"
      />
      {/* Right vine */}
      <path
        d="M144 10 Q170 10 200 8 Q230 6 260 10"
        stroke={color}
        strokeWidth="0.8"
        fill="none"
        opacity="0.6"
      />
      {/* Left leaves */}
      <path d="M80 8 Q78 5 82 6 Z" fill={color} opacity="0.5" />
      <path d="M50 9 Q48 6 52 7 Z" fill={color} opacity="0.5" />
      {/* Right leaves */}
      <path d="M200 8 Q198 5 202 6 Z" fill={color} opacity="0.5" />
      <path d="M230 9 Q228 6 232 7 Z" fill={color} opacity="0.5" />
      {/* End dots */}
      <circle cx="20" cy="10" r="1.5" fill={color} opacity="0.6" />
      <circle cx="260" cy="10" r="1.5" fill={color} opacity="0.6" />
    </svg>
  );
}

/* Variant B — wave with dots */
export function FlourishB({
  color = "var(--gold-deep)",
  width = 280,
  height = 16,
  className,
}: FlourishProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 280 16"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <path
        d="M10 8 Q30 3 50 8 Q70 13 90 8 Q110 3 130 8 Q150 13 170 8 Q190 3 210 8 Q230 13 250 8 Q265 4 270 8"
        stroke={color}
        strokeWidth="0.8"
        fill="none"
        opacity="0.5"
      />
      <circle cx="140" cy="8" r="2" fill={color} opacity="0.7" />
      <circle cx="70" cy="13" r="1.2" fill={color} opacity="0.4" />
      <circle cx="210" cy="13" r="1.2" fill={color} opacity="0.4" />
    </svg>
  );
}

/* Variant C — simple double line with central ornament */
export function FlourishC({
  color = "var(--gold-deep)",
  width = 280,
  height = 12,
  className,
}: FlourishProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 280 12"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <line x1="10" y1="5" x2="120" y2="5" stroke={color} strokeWidth="0.6" opacity="0.5" />
      <line x1="10" y1="7" x2="120" y2="7" stroke={color} strokeWidth="0.3" opacity="0.3" />
      <path d="M140 2 L144 6 L140 10 L136 6 Z" fill={color} opacity="0.7" />
      <line x1="160" y1="5" x2="270" y2="5" stroke={color} strokeWidth="0.6" opacity="0.5" />
      <line x1="160" y1="7" x2="270" y2="7" stroke={color} strokeWidth="0.3" opacity="0.3" />
    </svg>
  );
}

/* Variant D — asterism with trailing lines */
export function FlourishD({
  color = "var(--gold-deep)",
  width = 280,
  height = 16,
  className,
}: FlourishProps) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 280 16"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <line x1="10" y1="8" x2="115" y2="8" stroke={color} strokeWidth="0.5" opacity="0.4" />
      {/* Asterism ⁂ */}
      <text
        x="140"
        y="12"
        textAnchor="middle"
        fontSize="10"
        fill={color}
        opacity="0.7"
        fontFamily="serif"
      >
        ⁂
      </text>
      <line x1="165" y1="8" x2="270" y2="8" stroke={color} strokeWidth="0.5" opacity="0.4" />
    </svg>
  );
}
