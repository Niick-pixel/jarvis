// A machine that cannot give us WebGL is not a broken machine, and must not produce a blank app.
//
// Found by running the real UI on a box with no GPU: three.js throws while creating the context,
// the error escapes the lazy boundary, and React unmounts everything. Suspense does not catch
// throws, only promises - so this does.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  fallback: ReactNode;
  children: ReactNode;
}

export default class CanvasBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Local console only. Nothing about a failed render leaves this machine (rule 0.11).
    console.warn(
      "Background shader unavailable, using the CSS gradient instead:",
      error.message,
      info.componentStack,
    );
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
