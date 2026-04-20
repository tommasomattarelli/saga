/* Grain texture overlay — feTurbulence SVG, fixed, pointer-events-none */
export function NoiseOverlay() {
  return (
    <>
      <svg width="0" height="0" style={{ position: "absolute" }}>
        <defs>
          <filter id="saga-noise">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.65"
              numOctaves="3"
              stitchTiles="stitch"
            />
            <feColorMatrix type="saturate" values="0" />
          </filter>
        </defs>
      </svg>
      <div
        aria-hidden="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          pointerEvents: "none",
          filter: "url(#saga-noise)",
          opacity: 0.04,
          mixBlendMode: "multiply",
        }}
      />
    </>
  );
}
