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
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-parchment-900 text-parchment-300">
          <p className="font-display text-2xl text-gold-400">Something went wrong.</p>
          <p className="text-sm text-parchment-500">An unexpected error occurred.</p>
          <button
            onClick={() => window.location.reload()}
            className="rounded border border-gold-500/40 px-4 py-2 text-sm text-gold-400 hover:bg-parchment-800"
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
