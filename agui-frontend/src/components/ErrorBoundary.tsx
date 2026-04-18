import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(_error: Error): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: { componentStack: string }): void {
    console.error("ErrorBoundary caught:", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          background: "#0d0d1a",
          color: "#e0e0e0",
          fontFamily: "monospace",
        }}>
          <div style={{ fontSize: 14 }}>Something went wrong.</div>
          <button
            onClick={() => location.reload()}
            style={{
              background: "#0f3460",
              color: "#4a9eff",
              border: "1px solid #4a9eff",
              borderRadius: 4,
              padding: "8px 16px",
              fontFamily: "monospace",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
