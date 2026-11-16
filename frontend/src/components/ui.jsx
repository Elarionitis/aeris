import React from 'react';

/** Keeps one failing panel from taking down the whole dashboard. */
export class PanelErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surface it for debugging; the UI stays usable either way.
    console.error(`Panel "${this.props.title}" crashed`, error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <section className="card p-5">
          <h2 className="font-display text-base font-bold">{this.props.title}</h2>
          <p className="mt-2 text-sm text-muted">
            This panel failed to render. The rest of the dashboard is unaffected.
          </p>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-3 rounded-lg border border-edge bg-raised px-3 py-1.5 text-xs font-medium hover:bg-line"
          >
            Try again
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status" aria-live="polite">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-edge border-t-accent" />
      {label}…
    </div>
  );
}

export function ErrorNote({ message, onRetry }) {
  return (
    <div className="rounded-xl border border-accent/40 bg-accent/5 p-4" role="alert">
      <p className="text-sm leading-relaxed text-accent">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-lg border border-edge bg-raised px-3 py-1.5 text-xs font-medium text-ink hover:bg-line"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

/**
 * Standard panel chrome: title, optional subtitle and controls, and a body
 * that swaps between loading, error, and content.
 */
export function Panel({
  title,
  subtitle,
  actions,
  loading,
  error,
  onRetry,
  minHeight = 160,
  children,
  className = '',
}) {
  return (
    <section className={`card flex flex-col p-5 ${className}`}>
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-base font-bold leading-tight">{title}</h2>
          {subtitle ? <p className="mt-1 text-xs text-muted">{subtitle}</p> : null}
        </div>
        {actions}
      </header>
      <div className="flex-1" style={{ minHeight }}>
        {loading ? (
          <div className="grid h-full place-items-center" style={{ minHeight }}>
            <Spinner />
          </div>
        ) : error ? (
          <ErrorNote message={error} onRetry={onRetry} />
        ) : (
          children
        )}
      </div>
    </section>
  );
}

export function BandPill({ label, color }) {
  return (
    <span className="chip" title={`AQI band: ${label}`}>
      <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden="true" />
      {label}
    </span>
  );
}
