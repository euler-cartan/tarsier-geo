import { Ico } from "../components/Icon";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Bar, BarChart, Tooltip, XAxis, YAxis } from "recharts";
import {
  ChangeEvent,
  enableChangePolling,
  generateChangeReport,
  getChanges,
  installChangeTriggers,
  saveReportSchedule,
  syncChanges,
  VolumeBar,
} from "../api";
import { ErrorState, LoadingState } from "../components/States";
import StatusBadge from "../components/StatusBadge";
import TrackingHealthBanner from "../components/TrackingHealthBanner";
import { useAi } from "../shell/AiContext";
import { palette } from "../design";

/** FSD §10 / DVS §5–6 global Changes screen. */
function Changes() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const ai = useAi();
  const [data, setData] = useState<Awaited<ReturnType<typeof getChanges>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [user, setUser] = useState("");
  const [dayFilter, setDayFilter] = useState<string | null>(null);
  const [range, setRange] = useState<Record<string, string>>({});
  const [filterBusy, setFilterBusy] = useState(false);
  const [featureId, setFeatureId] = useState<string | null>(null);

  function load(extra: Record<string, string> = {}) {
    if (!connectionId) return;
    const params: Record<string, string> = {...range, ...extra};
    if (dayFilter) {params.start = dayFilter; params.end = dayFilter;}
    setFilterBusy(true);
    getChanges(connectionId, params)
      .then((body) => {
        setData(body);
        setError(null);
      })
      .catch((err) => setError(err.message)).finally(() => setFilterBusy(false));
  }

  useEffect(() => {
    load();
  }, [connectionId, range, dayFilter]);

  if (error && !data) {
    return <ErrorState message={error} onRetry={() => { setError(null); load(); }} />;
  }
  if (!data) return <LoadingState label="Loading changes" />;
  if (!data.available) {
    return (
      <div className="card">
        <h1 className="t-display-lg">Changes</h1>
        <p className="t-caption">{data.reason}</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-4)" }}>
        <h1 className="t-display-lg" style={{ margin: 0 }}>
          Changes
        </h1>
        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <button type="button" className="button-secondary-outline" onClick={() => ai.show({ job: "explain-changes" })}><Ico t="Explain today’s changes" /></button>
          <Toolbar connectionId={connectionId!} mode={data.mode} onDone={() => load()} onError={setError} />
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      {data.mode === "none" && <p className="t-caption">{data.reason}</p>}
      {data.mode === "polling" && (
        <p className="t-caption">Polling mode  -  Tarsier can see what changed, not who.</p>
      )}

      <TrackingHealthBanner connectionId={connectionId!} health={data.tracking_health} onReviewed={() => load()} />
      <VolumeChart bars={data.volume} onSelectDay={(d) => setDayFilter(d)} />

      <div className="card" style={{ marginTop: "var(--space-5)" }}>
        <h2 className="t-heading-lg" style={{marginTop: 0}}>Compare two dates</h2>
        <p className="t-caption">Review recorded changes between inclusive dates. For row-by-row version differences, use Snapshots.</p>
        <form className="filter-grid" onSubmit={e => {e.preventDefault(); if (start && end && start > end) {setError("Start date must be on or before end date."); return;} setDayFilter(null); setRange({...(start ? {start} : {}), ...(end ? {end} : {}), ...(user ? {user} : {})});}}>
          <label>From<input className="text-input" type="date" value={start} onChange={e => setStart(e.target.value)} /></label>
          <label>Through<input className="text-input" type="date" min={start || undefined} value={end} onChange={e => setEnd(e.target.value)} /></label>
          <label>Database user<input className="text-input" placeholder="All users" value={user} onChange={e => setUser(e.target.value)} /></label>
          <button className="button-primary-dark" disabled={filterBusy}><Ico t={filterBusy ? "Loading…" : "Compare dates"} /></button>
          <button type="button" className="button-secondary-outline" onClick={() => {setStart(""); setEnd(""); setUser(""); setDayFilter(null); setRange({});}}><Ico t="Clear filters" /></button>
        </form>
        <p role="status" className="t-caption">{dayFilter || `${range.start || "First recorded change"} to ${range.end || "today"}`} · {(data.total_events ?? data.events.length).toLocaleString()} recorded events{data.truncated ? ` · showing the newest ${data.events.length.toLocaleString()} - narrow the dates or filters to see older ones` : ""}</p>
        <div className="change-summary">{["insert", "update", "delete", "schema"].map(action => <div key={action}><strong>{(data.action_counts ? data.action_counts[action] ?? 0 : data.events.filter(e => e.action === action).length).toLocaleString()}</strong><span>{action === "schema" ? "Schema events" : `${action}s`}</span></div>)}</div>
      </div>

      <ReportCard connectionId={connectionId!} data={data} onDone={() => load()} onError={setError} />

      <ChangeFeed events={data.events} onOpenFeature={setFeatureId} />

      {featureId && (
        <FeatureTimeline
          events={data.events.filter((e) => e.feature_id === featureId)}
          featureId={featureId}
          onClose={() => setFeatureId(null)}
        />
      )}
    </div>
  );
}

function Toolbar({
  connectionId,
  mode,
  onDone,
  onError,
}: {
  connectionId: string;
  mode: string;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  async function run(fn: () => Promise<void>) {
    try {
      await fn();
      onDone();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not update change tracking.");
    }
  }
  return (
    <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
      <button type="button" className="button-primary-dark" onClick={() => run(() => installChangeTriggers(connectionId))}><Ico t="Install/Upgrade history log" /></button>
      {mode === "none" && (
        <button type="button" className="button-secondary-outline" onClick={() => run(() => enableChangePolling(connectionId))}><Ico t="Skip for now - use polling" /></button>
      )}
      {mode !== "none" && (
        <button type="button" className="button-secondary-outline" onClick={() => run(() => syncChanges(connectionId))}><Ico t="Sync now" /></button>
      )}
    </div>
  );
}

function VolumeChart({ bars, onSelectDay }: { bars: VolumeBar[]; onSelectDay: (date: string) => void }) {
  if (bars.every((b) => b.count === 0)) {
    return <p className="t-caption">No changes recorded in this range</p>;
  }
  const data = bars.map((b) => ({ ...b, fill: b.is_spike ? palette.danger : palette.primary }));
  return (
    <div className="card" style={{ marginTop: "var(--space-5)" }}>
      <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
        Change volume
      </h2>
      <BarChart width={720} height={180} data={data} margin={{ left: 8, right: 8 }}>
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--ink-mute)" }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--ink-mute)" }} />
        <Tooltip />
        <Bar
          dataKey="count"
          fill={palette.primary}
          shape={(props: { x?: number; y?: number; width?: number; height?: number; payload?: VolumeBar }) => {
            const { x = 0, y = 0, width = 0, height = 0, payload } = props;
            return (
              <rect
                x={x}
                y={y}
                width={width}
                height={height}
                fill={payload?.is_spike ? palette.danger : palette.primary}
                onClick={() => payload && onSelectDay(payload.date)}
                style={{ cursor: "pointer" }}
              />
            );
          }}
        />
      </BarChart>
    </div>
  );
}

function ReportCard({
  connectionId,
  data,
  onDone,
  onError,
}: {
  connectionId: string;
  data: NonNullable<Awaited<ReturnType<typeof getChanges>>>;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function perform(action: () => Promise<unknown>, message: string) {
    setBusy(true); setNotice("");
    try {await action(); setNotice(message); onDone();}
    catch (err) {onError(err instanceof Error ? err.message : "Could not update report.");}
    finally {setBusy(false);}
  }
  return <section className="card" style={{marginTop: "var(--space-5)"}}>
    <div className="page-heading"><div><h2 className="t-heading-lg">Auto change report</h2><p className="t-caption">Summaries use the recorded change log. Schedule times use UTC.</p></div><button className="button-primary-dark" disabled={busy} onClick={() => perform(() => generateChangeReport(connectionId, data.report_interval || "daily"), "Report generated from the recorded change log.")}><Ico t={busy ? "Working…" : "Generate now"} /></button></div>
    <div className="form-actions"><span className="t-caption">Automatic schedule</span>{["off", "daily", "weekly"].map(interval => <button key={interval} className={(data.report_interval || "off") === interval ? "button-primary-dark" : "button-secondary-outline"} aria-pressed={(data.report_interval || "off") === interval} disabled={busy} onClick={() => perform(() => saveReportSchedule(connectionId, interval), interval === "off" ? "Automatic reports disabled." : `Automatic ${interval} reports enabled.`)}>{interval === "off" ? "Off" : interval === "daily" ? "Daily" : "Weekly"}</button>)}<span className="t-caption">{data.report_interval ? `Active: ${data.report_interval}` : "No schedule set"}</span></div>
    {notice && <p role="status">{notice}</p>}
    {data.report ? <div className="search-plan"><strong>{data.report.interval} report</strong><p>{data.report.total} changes · {data.report.mass_batches || 0} mass-change batches</p><details><summary>View full report</summary><pre>{JSON.stringify(data.report, null, 2)}</pre></details></div> : <p className="t-caption">No report yet. Generate your first summary above.</p>}
  </section>;
}

function ChangeFeed({ events, onOpenFeature }: { events: ChangeEvent[]; onOpenFeature: (id: string) => void }) {
  return (
    <div className="card" style={{ marginTop: "var(--space-5)" }}>
      <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
        Change feed
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {events.map((event) => (
          <li key={event.id} style={{ marginBottom: "var(--space-3)" }}>
            <StatusBadge
              kind={event.action === "delete" ? "danger" : event.action === "insert" ? "good" : "info"}
              label={event.is_mass ? `${event.action} · mass change` : event.action}
            />{" "}
            <span className="t-caption">{event.occurred_at}</span>{" "}
            {event.db_user ?? "unknown  -  polling"} · {event.schema ? `${event.schema}.` : ""}
            {event.name}
            {event.feature_id && (
              <button type="button" className="button-secondary-outline" style={{ marginLeft: "var(--space-3)" }} onClick={() => onOpenFeature(event.feature_id!)}>
                Feature {event.feature_id}
              </button>
            )}
            {event.changed_fields.length > 0 && (
              <p className="t-caption" style={{ margin: "4px 0 0" }}>
                {event.changed_fields.join(", ")}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function FeatureTimeline({
  events,
  featureId,
  onClose,
}: {
  events: ChangeEvent[];
  featureId: string;
  onClose: () => void;
}) {
  const ordered = useMemo(
    () => [...events].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)),
    [events]
  );
  return (
    <div className="card" style={{ marginTop: "var(--space-5)" }}>
      <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
        Feature {featureId}
      </h2>
      <button type="button" className="button-secondary-outline" onClick={onClose}><Ico t="Close" /></button>
      <ol>
        {ordered.map((event) => (
          <li key={event.id} style={{ marginBottom: "var(--space-3)" }}>
            <strong>{event.action}</strong> · {event.occurred_at} · {event.db_user ?? "unknown  -  polling"}
            <Diff before={event.before} after={event.after} fields={event.changed_fields} />
          </li>
        ))}
      </ol>
    </div>
  );
}

export function Diff({
  before,
  after,
  fields,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  fields: string[];
}) {
  if (fields.length === 0) return null;
  return (
    <dl>
      {fields.map((field) => (
        <div key={field}>
          <dt className="t-caption">{field}</dt>
          <dd>
            <s style={{ color: "var(--ink-faint)" }}>{String(before?.[field] ?? " - ")}</s>{" "}
            {String(after?.[field] ?? " - ")}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default Changes;
