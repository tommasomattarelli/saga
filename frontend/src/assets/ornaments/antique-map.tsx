import { motion } from "framer-motion";

/* Antique fantasy map — full-bleed background.
   Continenti astratti, onde, rosa dei venti, creature marginali. Sottile rotazione 30s. */
interface AntiqueMapProps {
  animate?: boolean;
  className?: string;
}

export function AntiqueMap({ animate = true, className }: AntiqueMapProps) {
  const inkColor = "var(--ink-faded)";
  const strokeColor = "var(--gold-deep)";

  const Wrapper = animate ? motion.div : "div";
  const wrapperProps = animate
    ? {
        animate: { rotate: [-0.6, 0.6, -0.6] },
        transition: { duration: 30, repeat: Infinity, ease: "easeInOut" as const },
      }
    : {};

  return (
    <Wrapper
      className={className}
      {...(wrapperProps as object)}
      style={{
        position: "absolute",
        inset: "-5%",
        pointerEvents: "none",
      }}
    >
      <svg
        viewBox="0 0 1200 800"
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
      >
        {/* Defs — wave pattern */}
        <defs>
          <pattern id="waves" x="0" y="0" width="40" height="12" patternUnits="userSpaceOnUse">
            <path
              d="M 0 6 Q 10 2 20 6 T 40 6"
              stroke={inkColor}
              strokeWidth="0.4"
              fill="none"
              opacity="0.35"
            />
          </pattern>
          <filter id="parchment-blur">
            <feGaussianBlur stdDeviation="0.3" />
          </filter>
        </defs>

        {/* Ocean — waves pattern */}
        <rect width="1200" height="800" fill="url(#waves)" opacity="0.5" />

        {/* Latitude/longitude grid — molto tenue */}
        {[200, 400, 600].map((y) => (
          <line
            key={`lat-${y}`}
            x1="0"
            y1={y}
            x2="1200"
            y2={y}
            stroke={strokeColor}
            strokeWidth="0.3"
            opacity="0.12"
            strokeDasharray="2 6"
          />
        ))}
        {[300, 600, 900].map((x) => (
          <line
            key={`lon-${x}`}
            x1={x}
            y1="0"
            x2={x}
            y2="800"
            stroke={strokeColor}
            strokeWidth="0.3"
            opacity="0.12"
            strokeDasharray="2 6"
          />
        ))}

        {/* Continent 1 — REGNO (left) */}
        <g filter="url(#parchment-blur)">
          <path
            d="M 100 180 Q 90 140 130 120 Q 180 100 220 130 Q 260 115 290 145 Q 330 160 320 200 Q 340 240 300 260 Q 270 290 220 285 Q 170 300 130 275 Q 95 250 100 180 Z"
            fill={strokeColor}
            opacity="0.18"
            stroke={strokeColor}
            strokeWidth="0.6"
          />
          <text
            x="210"
            y="210"
            textAnchor="middle"
            fontSize="14"
            fill={strokeColor}
            opacity="0.7"
            fontFamily="var(--font-display)"
            letterSpacing="0.2em"
          >
            REGNO
          </text>
          <text
            x="210"
            y="228"
            textAnchor="middle"
            fontSize="9"
            fill={inkColor}
            opacity="0.5"
            fontFamily="var(--font-body)"
            fontStyle="italic"
          >
            di Aureth
          </text>
        </g>

        {/* Continent 2 — ISLE (top right) */}
        <g filter="url(#parchment-blur)">
          <path
            d="M 860 120 Q 870 100 910 110 Q 950 95 980 120 Q 1000 145 985 175 Q 975 200 935 205 Q 895 210 875 185 Q 855 160 860 120 Z"
            fill={strokeColor}
            opacity="0.16"
            stroke={strokeColor}
            strokeWidth="0.6"
          />
          <text
            x="925"
            y="160"
            textAnchor="middle"
            fontSize="12"
            fill={strokeColor}
            opacity="0.7"
            fontFamily="var(--font-display)"
            letterSpacing="0.18em"
          >
            ISLE
          </text>
        </g>

        {/* Continent 3 — TERRA INCOGNITA (center bottom) */}
        <g filter="url(#parchment-blur)">
          <path
            d="M 480 420 Q 450 400 440 440 Q 420 470 430 510 Q 410 550 450 580 Q 490 620 560 625 Q 640 630 710 605 Q 770 585 780 540 Q 795 500 770 470 Q 740 440 680 430 Q 620 415 560 420 Q 510 425 480 420 Z"
            fill={strokeColor}
            opacity="0.2"
            stroke={strokeColor}
            strokeWidth="0.7"
          />
          <text
            x="605"
            y="520"
            textAnchor="middle"
            fontSize="16"
            fill={strokeColor}
            opacity="0.75"
            fontFamily="var(--font-display)"
            letterSpacing="0.22em"
          >
            TERRA
          </text>
          <text
            x="605"
            y="545"
            textAnchor="middle"
            fontSize="14"
            fill={strokeColor}
            opacity="0.7"
            fontFamily="var(--font-display)"
            letterSpacing="0.2em"
            fontStyle="italic"
          >
            INCOGNITA
          </text>
        </g>

        {/* Small island cluster (bottom right) */}
        <g opacity="0.5">
          <circle cx="1040" cy="540" r="14" fill={strokeColor} opacity="0.2" />
          <circle cx="1080" cy="570" r="8" fill={strokeColor} opacity="0.2" />
          <circle cx="1060" cy="590" r="10" fill={strokeColor} opacity="0.2" />
          <circle cx="1110" cy="540" r="6" fill={strokeColor} opacity="0.2" />
        </g>

        {/* Compass rose (top left corner area) */}
        <g transform="translate(140, 680)" opacity="0.55">
          <circle cx="0" cy="0" r="50" fill="none" stroke={strokeColor} strokeWidth="0.5" />
          <circle cx="0" cy="0" r="40" fill="none" stroke={strokeColor} strokeWidth="0.3" />
          {/* Cardinal arms */}
          <path d="M 0 -48 L 4 0 L 0 48 L -4 0 Z" fill={strokeColor} opacity="0.7" />
          <path d="M -48 0 L 0 4 L 48 0 L 0 -4 Z" fill={strokeColor} opacity="0.6" />
          {/* Diagonal arms */}
          <path
            d="M -34 -34 L 2 -2 L 34 34 L -2 2 Z"
            fill={strokeColor}
            opacity="0.4"
            transform="rotate(0)"
          />
          <path d="M 34 -34 L -2 -2 L -34 34 L 2 2 Z" fill={strokeColor} opacity="0.4" />
          {/* Cardinals */}
          <text
            x="0"
            y="-54"
            textAnchor="middle"
            fontSize="8"
            fill={strokeColor}
            fontFamily="var(--font-display)"
          >
            N
          </text>
          <text
            x="56"
            y="3"
            textAnchor="middle"
            fontSize="8"
            fill={strokeColor}
            fontFamily="var(--font-display)"
          >
            E
          </text>
          <text
            x="0"
            y="62"
            textAnchor="middle"
            fontSize="8"
            fill={strokeColor}
            fontFamily="var(--font-display)"
          >
            S
          </text>
          <text
            x="-56"
            y="3"
            textAnchor="middle"
            fontSize="8"
            fill={strokeColor}
            fontFamily="var(--font-display)"
          >
            W
          </text>
        </g>

        {/* Sea creature — dragon (right side) */}
        <g transform="translate(1040, 280)" opacity="0.55">
          {/* Dragon serpent body */}
          <path
            d="M -40 0 Q -20 -12 0 -4 Q 20 4 40 -8 Q 60 -4 70 8"
            stroke={strokeColor}
            strokeWidth="1.2"
            fill="none"
            strokeLinecap="round"
          />
          {/* Dragon head */}
          <path d="M 70 8 Q 78 4 80 10 Q 82 16 76 18 Q 72 20 70 16 Z" fill={strokeColor} />
          {/* Wings */}
          <path d="M 10 -6 Q 18 -18 28 -14 Q 22 -8 10 -6 Z" fill={strokeColor} opacity="0.5" />
          <path d="M 40 -10 Q 50 -22 58 -14 Q 50 -10 40 -10 Z" fill={strokeColor} opacity="0.5" />
          {/* Scales dots */}
          <circle cx="-10" cy="-4" r="0.8" fill={strokeColor} />
          <circle cx="20" cy="0" r="0.8" fill={strokeColor} />
          <circle cx="50" cy="-4" r="0.8" fill={strokeColor} />
        </g>

        {/* Sea creature — whale (bottom left) */}
        <g transform="translate(280, 700)" opacity="0.5">
          <path
            d="M 0 0 Q 30 -10 60 0 Q 80 6 90 -2 L 85 4 L 90 10 Q 80 14 60 12 Q 30 16 0 6 Q -10 4 -10 2 Q -6 -2 0 0 Z"
            fill={strokeColor}
            opacity="0.5"
          />
          {/* Spout */}
          <path
            d="M 30 -12 Q 28 -18 32 -22 Q 36 -18 34 -12"
            stroke={strokeColor}
            strokeWidth="0.6"
            fill="none"
            opacity="0.6"
          />
          <circle cx="60" cy="-4" r="1" fill="var(--parchment-base)" opacity="0.3" />
        </g>

        {/* Scroll banner top — "HERE BE DRAGONS" */}
        <text
          x="870"
          y="270"
          fontSize="9"
          fill={inkColor}
          opacity="0.45"
          fontFamily="var(--font-display)"
          letterSpacing="0.3em"
        >
          HIC SUNT DRACONES
        </text>
      </svg>
    </Wrapper>
  );
}
