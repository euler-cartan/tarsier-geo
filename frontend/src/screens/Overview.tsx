import { Ico } from "../components/Icon";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getOverview, OverviewSummary } from "../api";
import { formatBytes, formatDate } from "../format";
import HealthRing from "../components/HealthRing";
import LayerTable from "../components/LayerTable";
import ProjectionChart from "../components/ProjectionChart";
import { ErrorState } from "../components/States";
import OverviewSkeleton from "./OverviewSkeleton";

/** FSD §6  -  Overview, PRD §7.1 (Feature A). */
function Overview() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [job, setJob] = useState<{state: string; message: string; completed: number; total: number; errors?: {schema: string; name: string; check: string; message: string}[]; skipped?: {schema: string; name: string; check: string; message: string}[]} | null>(null);
  const [projectionFilter, setProjectionFilter] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!connectionId) return;
    getOverview(connectionId)
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }, [connectionId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!connectionId) return;
    let cancelled = false;
    async function poll() {
      try {
        const response = await fetch(`/api/connections/${connectionId}/checks`);
        if (response.status === 404) {
          // The connection was removed (or the link is stale). Say so, and stop asking.
          cancelled = true;
          setError("This connection no longer exists. Choose another from your connections.");
          return;
        }
        if (!response.ok) throw Error();
        const current = await response.json();
        if (cancelled || !current.state) return;
        setJob(current); setScanning(current.state === "running");
        if (current.state !== "idle") load();
      } catch { if (!cancelled) setError("Could not read check progress. Retry to reconnect to the app."); }
    }
    void poll();
    const timer = window.setInterval(poll, 1500);
    return () => {cancelled = true; window.clearInterval(timer);};
  }, [connectionId, load]);

  async function runCheck() {
    if (!connectionId) return;
    setScanning(true);
    setError(null);
    try {
      const response = await fetch(`/api/connections/${connectionId}/checks`, {method: "POST"});
      if (!response.ok) throw Error("Could not start the health check.");
      setJob(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run the check.");
      setScanning(false);
    }
  }

  if (error) {
    return <ErrorState message={error} onRetry={() => { setError(null); load(); }} />;
  }

  if (!summary) {
    return <OverviewSkeleton />;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "var(--space-8)" }}>
        <div>
          <p className="t-label" style={{ marginBottom: "var(--space-3)" }}>Overview</p>
          <h1 className="t-display-xl" style={{ marginBottom: "var(--space-3)" }}>{summary.connection_name}</h1>
          <span className="t-caption">
            {summary.connection_type} · {summary.ever_scanned ? `Last checked ${formatDate(summary.last_scanned_at)}` : "Never checked"}
          </span>
        </div>
        <button className="button-secondary-outline" onClick={runCheck} disabled={scanning}><Ico t={scanning ? "Running…" : "Run full check"} /></button>
      </div>

      {summary.no_permission_count > 0 && <p role="status" className="card" style={{ padding: "var(--space-4)", marginBottom: "var(--space-5)" }}>{summary.no_permission_count} {summary.no_permission_count === 1 ? "table" : "tables"} shown with no permission.</p>}
      {summary.source_notice && <p role="status" className="card" style={{ padding: "var(--space-4)", marginBottom: "var(--space-5)" }}>{summary.source_notice}</p>}
      {job && job.state !== "idle" && <div className="check-progress card" role="status" aria-live="polite" aria-busy={scanning}><strong>{job.message}</strong>{scanning && <progress aria-label="Full health check progress" max={Math.max(1, job.total)} value={job.completed} />}<p className="t-caption">{job.total > 0 ? `${job.completed} of ${job.total} steps finished. ` : ""}{scanning ? "You can keep using the app while the check runs." : ""}</p>{!!job.skipped?.length && <details open><summary>{job.skipped.length} statistics checks used samples</summary>{job.skipped.map((e,i) => <p key={i} className="t-caption">{e.schema}.{e.name}: {e.message}</p>)}</details>}{!!job.errors?.length && <details><summary>{job.errors.length} checks need attention</summary>{job.errors.map((e,i) => <p key={i} className="t-caption">{e.schema}.{e.name}: {e.check}. {e.message}</p>)}</details>}</div>}
      {!summary.ever_scanned ? (
        <div className="orb-card" style={{ padding: "var(--space-9) var(--space-7)" }}>
          <p className="t-display-md" style={{ marginBottom: "var(--space-6)" }}>No check has run yet for this connection.</p>
          <button className="button-primary-dark" onClick={runCheck} disabled={scanning}><Ico t={scanning ? "Running…" : "Run first check"} /></button>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: "var(--space-5)", marginBottom: "var(--space-6)" }}>
            <StatCard label="Overall health">
              {scanning ? <p role="status" className="t-caption">Checking your layers. Health results will appear shortly.</p> : <HealthRing isSample={summary.health_is_sample} score={summary.health_score} components={summary.health_components} componentsAreAverages coverageCount={summary.health_coverage_count} totalLayers={summary.total_layers} />}
            </StatCard>
            <StatCard label="Total layers">
              <span className="t-stat-xl">{summary.total_layers}</span>
            </StatCard>
            <StatCard label="Total size">
              <span className="t-stat-xl">{formatBytes(summary.total_size_bytes)}</span>
            </StatCard>
            <StatCard label="Last change detected">
              <span className="t-body-lg" style={{ color: "var(--ink-faint)" }}>Not tracked yet</span>
            </StatCard>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)", marginBottom: "var(--space-8)" }}>
            <div className="card">
              <h2 className="t-heading-lg" style={{ marginBottom: "var(--space-4)" }}>Relationships</h2>
              <p className="t-caption">{summary.relationship_count} {summary.relationship_count === 1 ? "connection" : "connections"} found.</p>
              <Link className="t-body-md" to={`/connections/${connectionId}/flowchart`}>Open full flowchart →</Link>
            </div>
            <div className="card">
              <h2 className="t-heading-lg" style={{ marginBottom: "var(--space-4)" }}>Projection overview</h2>
              <ProjectionChart
                projections={summary.projections}
                onSelect={(srid) => setProjectionFilter((current) => (current === srid ? null : srid))}
              />
              {projectionFilter !== null && (
                <button className="button-secondary-outline" style={{ marginTop: "var(--space-3)" }} onClick={() => setProjectionFilter(null)}><Ico t="Clear filter" /></button>
              )}
            </div>
          </div>

          <h2 className="t-display-sm" style={{ marginBottom: "var(--space-5)" }}>Layers</h2>
          <LayerTable layers={summary.layers} projectionFilter={projectionFilter} />
        </>
      )}
    </div>
  );
}

function StatCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="t-label">{label}</div>
      <div style={{ marginTop: "var(--space-5)" }}>{children}</div>
    </div>
  );
}

export default Overview;
