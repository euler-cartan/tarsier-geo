import { Ico } from "./Icon";
import { ReactNode } from "react";

/** FSD §15 / DVS §15  -  the shared building blocks for the states every data screen must handle. */

/** Loading: skeleton placeholders shaped like content, never a bare spinner or blank area. */
export function LoadingState({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 44 : 84, marginBottom: "var(--space-4)" }} />
      ))}
    </div>
  );
}

/** Error: plain-language message in status-danger text, with a retry action where there is one. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      style={{
        margin: "var(--space-4) 0",
        padding: "var(--space-5) var(--space-6)",
        background: "#fef2f2",
        border: "1px solid #fecaca",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <p style={{ color: "var(--status-danger)", margin: "0 0 var(--space-3)" }}>{message}</p>
      {onRetry && (
        <button type="button" className="button-secondary-outline" onClick={onRetry}><Ico t="Retry" /></button>
      )}
    </div>
  );
}

/** Empty: a clear explanation plus the next action. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="orb-card" style={{ padding: "var(--space-8) var(--space-7)" }}>
      <h2 className="t-display-sm" style={{ marginBottom: "var(--space-3)" }}>
        {title}
      </h2>
      {children && (
        <p className="t-body-md" style={{ color: "var(--ink-body)", maxWidth: 520, margin: "0 auto var(--space-6)" }}>
          {children}
        </p>
      )}
      {action}
    </div>
  );
}

/** Not applicable / partial: expected behaviour for a tiered feature, in ink-faint, not an error colour. */
export function NotApplicable({ children }: { children: ReactNode }) {
  return (
    <p className="t-caption" style={{ color: "var(--ink-faint)" }}>
      {children}
    </p>
  );
}
