import { motion } from "framer-motion";

interface CandleProps {
  height?: number;
  className?: string;
  animate?: boolean;
}

/* Animated candle SVG — fiamma vivente via framer-motion keyframes */
export function Candle({ height = 180, className, animate = true }: CandleProps) {
  return (
    <svg
      width={height * 0.35}
      height={height}
      viewBox="0 0 60 180"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <radialGradient id="flame-grad" cx="50%" cy="60%" r="50%">
          <stop offset="0%" stopColor="#FFE8A0" stopOpacity="1" />
          <stop offset="40%" stopColor="#FFB84D" stopOpacity="0.95" />
          <stop offset="80%" stopColor="#D4711A" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#8B0000" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="glow-grad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#FFB84D" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#FFB84D" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="wax-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#F4E8D0" />
          <stop offset="100%" stopColor="#D4B888" />
        </linearGradient>
      </defs>

      {/* Ambient glow */}
      <motion.ellipse
        cx="30"
        cy="36"
        rx="32"
        ry="26"
        fill="url(#glow-grad)"
        animate={animate ? { opacity: [0.7, 1, 0.7], scale: [1, 1.08, 1] } : undefined}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Flame — group pivot at the base */}
      <motion.g
        style={{ transformOrigin: "30px 50px", transformBox: "view-box" } as React.CSSProperties}
        animate={
          animate
            ? {
                scaleY: [1, 1.05, 0.98, 1.03, 1],
                scaleX: [1, 0.97, 1.02, 0.98, 1],
                rotate: [0, -2, 1.5, -1, 0],
              }
            : undefined
        }
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      >
        {/* Outer flame */}
        <path
          d="M 30 14 Q 22 28 24 40 Q 26 48 30 50 Q 34 48 36 40 Q 38 28 30 14 Z"
          fill="url(#flame-grad)"
        />
        {/* Inner flame */}
        <path
          d="M 30 22 Q 27 32 28 42 Q 30 46 32 42 Q 33 32 30 22 Z"
          fill="#FFE8A0"
          opacity="0.9"
        />
        {/* Hottest center */}
        <ellipse cx="30" cy="40" rx="1.5" ry="3" fill="#FFFFFF" opacity="0.7" />
      </motion.g>

      {/* Wick */}
      <rect x="29.2" y="50" width="1.6" height="4" fill="#2a1a10" />

      {/* Wax body */}
      <rect
        x="20"
        y="54"
        width="20"
        height="112"
        fill="url(#wax-grad)"
        stroke="var(--gold-deep)"
        strokeWidth="0.4"
      />

      {/* Wax drips (static) */}
      <path
        d="M 20 74 Q 18 86 20 92 L 22 90 Q 21 84 22 76 Z"
        fill="var(--parchment-base)"
        opacity="0.85"
      />
      <path
        d="M 40 100 Q 42 108 40 118 L 38 116 Q 39 110 38 102 Z"
        fill="var(--parchment-base)"
        opacity="0.8"
      />

      {/* Base */}
      <rect
        x="16"
        y="166"
        width="28"
        height="10"
        fill="var(--gold-deep)"
        stroke="var(--gold)"
        strokeWidth="0.5"
      />
      <ellipse cx="30" cy="176" rx="18" ry="3" fill="rgba(0,0,0,0.4)" />
    </svg>
  );
}
