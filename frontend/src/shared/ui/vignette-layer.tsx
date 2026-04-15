/* Vignette layer — radial gradient fixed overlay, pointer-events-none */
export function VignetteLayer() {
  return (
    <div
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1,
        pointerEvents: "none",
        background:
          "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.45) 100%)",
      }}
    />
  );
}
