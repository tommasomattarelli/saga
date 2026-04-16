import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { CornerFlourish } from "../../assets/ornaments/corner-flourish";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="relative flex min-h-screen flex-col items-center justify-center"
          style={{ background: "var(--parchment-base)" }}
        >
          {/* Corner flourishes */}
          <span className="absolute top-6 left-6">
            <CornerFlourish corner="tl" size={36} />
          </span>
          <span className="absolute top-6 right-6">
            <CornerFlourish corner="tr" size={36} />
          </span>
          <span className="absolute bottom-6 left-6">
            <CornerFlourish corner="bl" size={36} />
          </span>
          <span className="absolute bottom-6 right-6">
            <CornerFlourish corner="br" size={36} />
          </span>

          {/* Torn parchment glyph */}
          <div
            className="mb-6 font-display"
            style={{ fontSize: 64, color: "var(--gold-deep)", opacity: 0.4 }}
            aria-hidden="true"
          >
            ✦
          </div>

          <h1
            className="font-display text-3xl uppercase mb-3 text-center"
            style={{ color: "var(--gold-bright)", letterSpacing: "0.22em" }}
          >
            The Weave tears…
          </h1>

          <p
            className="font-body italic text-lg mb-8 text-center max-w-sm"
            style={{ color: "var(--ink-secondary)" }}
          >
            Something has gone awry in the fabric of the tale.
          </p>

          {/* Ornate button */}
          <button
            onClick={() => window.location.reload()}
            className="font-display text-sm uppercase tracking-grimoire-wide px-8 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-bright active:scale-95 transition-transform"
            style={{
              color: "var(--gold-bright)",
              border: "1px solid var(--gold-bright)",
              outline: "1px solid var(--gold-deep)",
              outlineOffset: "3px",
              background: "rgba(212, 175, 55, 0.08)",
            }}
          >
            Restore
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
