import { motion } from "framer-motion";

interface SagaSealProps {
  size?: number;
  color?: string;
  animate?: boolean;
  className?: string;
}

/* SAGA sigillo — cerchi concentrici, 8 stelle equidistanti, S centrale in Cinzel Decorative,
   stroke-draw animation opzionale al mount */
export function SagaSeal({
  size = 120,
  color = "var(--gold-bright)",
  animate = true,
  className,
}: SagaSealProps) {
  const stars = Array.from({ length: 8 }, (_, i) => {
    const angle = (i / 8) * Math.PI * 2 - Math.PI / 2;
    const r = 52;
    const cx = 64 + r * Math.cos(angle);
    const cy = 64 + r * Math.sin(angle);
    return { cx, cy };
  });

  const MotionCircle = animate ? motion.circle : "circle";
  const MotionPath = animate ? motion.path : "path";

  const strokeDraw = animate
    ? {
        initial: { pathLength: 0, opacity: 0 },
        animate: { pathLength: 1, opacity: 1 },
        transition: { duration: 1.6, ease: "easeInOut" as const },
      }
    : {};

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      aria-hidden="true"
      className={className}
      style={{ overflow: "visible" }}
    >
      {/* Outer ring */}
      <MotionCircle
        cx={64}
        cy={64}
        r={60}
        fill="none"
        stroke={color}
        strokeWidth={1.2}
        opacity={0.85}
        {...(strokeDraw as object)}
      />
      {/* Middle ring */}
      <MotionCircle
        cx={64}
        cy={64}
        r={46}
        fill="none"
        stroke={color}
        strokeWidth={0.8}
        opacity={0.55}
        {...(strokeDraw as object)}
      />
      {/* Inner ring (around letter) */}
      <MotionCircle
        cx={64}
        cy={64}
        r={28}
        fill="none"
        stroke={color}
        strokeWidth={1}
        opacity={0.7}
        {...(strokeDraw as object)}
      />

      {/* 8 points stars between middle and outer ring */}
      {stars.map((s, i) => (
        <MotionPath
          key={i}
          d={`M ${s.cx} ${s.cy - 3} L ${s.cx + 1} ${s.cy - 1} L ${s.cx + 3} ${s.cy} L ${s.cx + 1} ${s.cy + 1} L ${s.cx} ${s.cy + 3} L ${s.cx - 1} ${s.cy + 1} L ${s.cx - 3} ${s.cy} L ${s.cx - 1} ${s.cy - 1} Z`}
          fill={color}
          opacity={0.75}
          {...(strokeDraw as object)}
        />
      ))}

      {/* 4 cardinal flourishes (N/E/S/W lines into outer ring) */}
      {[0, 90, 180, 270].map((deg) => (
        <g key={deg} transform={`rotate(${deg} 64 64)`}>
          <MotionPath
            d="M 64 4 L 64 12"
            stroke={color}
            strokeWidth={0.8}
            opacity={0.6}
            strokeLinecap="round"
            {...(strokeDraw as object)}
          />
        </g>
      ))}

      {/* Central S — Cinzel Decorative */}
      <motion.text
        x={64}
        y={78}
        textAnchor="middle"
        fontSize={44}
        fontFamily="var(--font-display)"
        fontWeight={700}
        fill={color}
        initial={animate ? { opacity: 0, scale: 0.8 } : false}
        animate={animate ? { opacity: 1, scale: 1 } : false}
        transition={{ duration: 0.6, delay: 1.2, ease: "easeOut" }}
        style={{ letterSpacing: "0.04em" }}
      >
        S
      </motion.text>
    </svg>
  );
}
