import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getConnections, getOverview, OverviewSummary, SavedConnection } from "../api";
import { ErrorState, LoadingState } from "../components/States";
import HealthRing from "../components/HealthRing";

/** FSD §4: Connection list / Welcome. */
function ConnectionList() {
  const [connections, setConnections] = useState<SavedConnection[] | null>(null);
  const [health, setHealth] = useState<Record<string, OverviewSummary | null>>({});
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    getConnections().then((items) => {
      setConnections(items);
      void Promise.all(items.map(async (item) => {
        try { return [item.id, await getOverview(item.id)] as const; }
        catch { return [item.id, null] as const; }
      })).then((results) => setHealth(Object.fromEntries(results)));
    }).catch((err) => setError(err.message));
  }

  useEffect(load, []);

  if (error) {
    return <ErrorState message={`Could not load your connections: ${error}`} onRetry={load} />;
  }
  if (!connections) {
    return <LoadingState label="Loading connections" />;
  }

  if (connections.length === 0) {
    return (
      <div className="orb-card" style={{ padding: "var(--space-9) var(--space-7)", marginTop: "var(--space-6)" }}>
        <p className="t-label" style={{ marginBottom: "var(--space-5)" }}>A health record for your geospatial data</p>
        <h1 className="t-display-mega" style={{ maxWidth: 760, margin: "0 auto var(--space-6)" }}>Connect your first database.</h1>
        <p className="t-body-lg" style={{ color: "var(--ink-body)", fontWeight: 400, maxWidth: 560, margin: "0 auto var(--space-7)" }}>
          Tarsier watches your geospatial database and shows its health, statistics, and change
          history  -  no SQL required.
        </p>
        <Link to="/connections/new" className="button-primary-dark"><Ico t="Add a connection" /></Link>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "var(--space-7)" }}>
        <div>
          <p className="t-label" style={{ marginBottom: "var(--space-3)" }}>Workspace</p>
          <h1 className="t-display-xl">Your connections</h1>
        </div>
        <Link to="/connections/new" className="button-primary-dark"><Ico t="Add connection" /></Link>
      </div>
      <div style={{ display: "grid", gap: "var(--space-5)", gridTemplateColumns: "repeat(3, 1fr)" }}>
        {connections.map((c) => (
          <Link key={c.id} to={`/connections/${c.id}/overview`} className="card" style={{ textDecoration: "none", color: "var(--ink)" }}>
            <span className="badge-pill" style={{ marginBottom: "var(--space-5)" }}>{c.type}</span>
            <div className="t-display-sm">{c.name}</div>
            <div style={{ marginTop: "var(--space-3)" }}>
              <HealthRing score={health[c.id]?.health_score ?? null} coverageCount={health[c.id]?.health_coverage_count} totalLayers={health[c.id]?.total_layers} size="small" />
            </div>
            <div className="t-caption" style={{ marginTop: "var(--space-5)" }}>
              {c.last_checked_at ? `Last checked ${new Date(c.last_checked_at).toLocaleString()}` : "Never checked"}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default ConnectionList;
