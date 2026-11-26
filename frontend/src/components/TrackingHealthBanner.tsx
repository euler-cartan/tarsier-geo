import { Ico } from "./Icon";
import { useState } from "react";
import { acknowledgeTrackingFailures, TrackingHealth } from "../api";

export default function TrackingHealthBanner({ connectionId, health, onReviewed }: {
  connectionId: string; health?: TrackingHealth; onReviewed: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!health || ["polling", "not_enabled"].includes(health.status)) return null;
  const failures = health.logging_failures;
  const reviewed = !!health.acknowledged_at && failures != null && failures <= (health.acknowledged_failures ?? 0);
  const messages: string[] = [];
  if (health.status === "unavailable") messages.push("Tracking health could not be verified. This history may be incomplete.");
  if (health.logger_version === "legacy_or_modified") messages.push("Change tracking needs an update. Contact the connection owner.");
  if (health.missing_trigger_count) messages.push("Change tracking is incomplete because one or more tracking triggers are missing.");
  if (failures && !reviewed) messages.push("Some changes may be missing from this history.");
  if (!messages.length && !reviewed) return null;
  const warning = messages.length > 0;
  async function review() {
    setBusy(true); setError(null);
    try { await acknowledgeTrackingFailures(connectionId, failures!); onReviewed(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not mark as reviewed."); }
    finally { setBusy(false); }
  }
  return <div className="card" role={warning ? "alert" : "status"} style={{ marginBlock: "var(--space-4)", borderLeft: `3px solid var(${warning ? "--status-warning" : "--ink-mute"})` }}>
    {messages.map(message => <p key={message} className="t-body-md">{message}</p>)}
    {reviewed && <p className="t-caption">Reviewed on {new Date(health.acknowledged_at!).toLocaleString()}. Earlier possible gaps were acknowledged; this does not mean the missing changes were recovered.</p>}
    {!reviewed && failures != null && failures > 0 && <button type="button" className="button-secondary-outline" disabled={busy} onClick={review}><Ico t={busy ? "Saving…" : "Mark as reviewed"} /></button>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
