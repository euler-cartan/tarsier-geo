import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { CachedItem, ChangeEvent, getChanges, syncChanges } from "../api";
import { Diff } from "./Changes";
import StatusBadge from "../components/StatusBadge";
import TrackingHealthBanner from "../components/TrackingHealthBanner";
import type { TrackingHealth } from "../api";
import { ErrorState, NotApplicable } from "../components/States";

function HistoryPanel({ connectionId, item }: { connectionId: string; item: CachedItem }) {
  const [events, setEvents] = useState<ChangeEvent[] | null>(null);
  const [available, setAvailable] = useState(true);
  const [health, setHealth] = useState<TrackingHealth>();
  const [reason, setReason] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  function load() {
    setError(null);
    getChanges(connectionId, { schema: item.schema, name: item.name })
      .then((body) => {
        setAvailable(body.available);
        setHealth(body.tracking_health);
        setReason(body.reason);
        setEvents(body.events);
      })
      .catch((err) => setError(err.message));
  }

  useEffect(load, [connectionId, item.schema, item.name]);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }
  if (!events) return <div className="skeleton" style={{ height: 120 }} />;
  if (!available) {
    return (
      <div className="card">
        <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
          History
        </h2>
        <NotApplicable>{reason}</NotApplicable>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
        History
      </h2>
      <TrackingHealthBanner connectionId={connectionId} health={health} onReviewed={load} />
      <button type="button" className="button-secondary-outline" onClick={() => syncChanges(connectionId).then(load)}><Ico t="Sync now" /></button>
      {events.length === 0 && <p className="t-caption">No changes recorded for this layer yet.</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {events.map((event) => (
          <li key={event.id} style={{ marginTop: "var(--space-3)" }}>
            <StatusBadge kind={event.action === "delete" ? "danger" : "info"} label={event.action} />{" "}
            {event.occurred_at} · {event.db_user ?? "unknown  -  polling"} · feature {event.feature_id ?? " - "}
            {event.is_mass && <StatusBadge kind="danger" label="mass change" />}
            <button type="button" className="button-secondary-outline" onClick={() => setOpenId(openId === event.id ? null : event.id)}><Ico t={openId === event.id ? "Hide diff" : "Show diff"} /></button>
            {openId === event.id && <Diff before={event.before} after={event.after} fields={event.changed_fields} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default HistoryPanel;
