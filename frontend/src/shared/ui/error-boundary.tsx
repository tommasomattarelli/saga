import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

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
          className="flex min-h-screen flex-col items-center justify-center"
          style={{ background: "var(--parchment-base)" }}
        >
          <h1
            className="mb-2 text-center font-display text-lg font-semibold"
            style={{ color: "var(--ink-primary)" }}
          >
            Something went wrong
          </h1>

          <p
            className="mb-8 max-w-sm text-center font-display text-sm"
            style={{ color: "var(--ink-faded)" }}
          >
            Reload the page to continue your story.
          </p>

          <button
            onClick={() => window.location.reload()}
            className="rounded-lg px-6 py-2.5 font-display text-sm font-semibold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={{ color: "var(--accent)", border: "1px solid var(--accent)" }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
