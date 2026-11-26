import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CachedItem, getItem } from "../api";
import { formatBytes, formatDate, formatRowCount } from "../format";
import HealthRing from "../components/HealthRing";
import MapPreview from "../components/MapPreview";
import StatusBadge from "../components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import ConnectionsPanel from "./ConnectionsPanel";
import HistoryPanel from "./HistoryPanel";
import QualityPanel from "./QualityPanel";
import RasterPanel from "./RasterPanel";
import TabularPanel from "./TabularPanel";
import StatisticsPanel, { FlagKey } from "./StatisticsPanel";
import type { FeatureCollection } from "geojson";

const KIND_LABEL: Record<string, string> = { vector: "Vector layer", raster: "Raster", tabular: "Table" };

type Tab = "overview" | "statistics" | "quality" | "history" | "connections";
const TABS: Tab[] = ["statistics", "quality", "history", "connections"];
const FLAG_KEYS: FlagKey[] = ["messy", "out_of_range", "duplicates", "map_outliers", "null_geometry"];

/** FSD §7  -  Layer/Table/Raster detail page. Quality is hidden for raster. */
function ItemDetail() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [searchParams] = useSearchParams();
  const schema = searchParams.get("schema") ?? "";
  const name = searchParams.get("name") ?? "";
  const requestedTab = searchParams.get("tab");
  const rawFlag = searchParams.get("flag");
  const requestedFlag = rawFlag && FLAG_KEYS.includes(rawFlag as FlagKey) ? rawFlag as FlagKey : null;

  const [item, setItem] = useState<CachedItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkMessage, setCheckMessage] = useState("");
  const [checkFinished, setCheckFinished] = useState(false);
  const [tab, setTab] = useState<Tab>(() => TABS.includes(requestedTab as Tab) ? (requestedTab as Tab) : "overview");

  useEffect(() => {
    setTab(TABS.includes(requestedTab as Tab) ? (requestedTab as Tab) : "overview");
  }, [requestedTab]);

  function loadItem() {
    if (!connectionId || !name) return;
    setError(null);
    getItem(connectionId, schema, name)
      .then(setItem)
      .catch((err) => setError(err.message));
  }

  useEffect(() => {setItem(null); loadItem();}, [connectionId, schema, name]);

  useEffect(() => {
    let cancelled = false, timer: number | undefined;
    setCheckMessage("");
    setCheckFinished(false);
    async function poll() {
      try {
        const response = await fetch(`/api/connections/${connectionId}/checks`);
        if (!response.ok) throw Error();
        const job = await response.json();
        if (cancelled) return;
        setCheckFinished(Boolean(job.state?.startsWith("completed")));
        if (job.state === "running") {setCheckMessage(job.message); loadItem(); timer = window.setTimeout(poll, 2000);}
        else {setCheckMessage(""); if (job.state?.startsWith("completed")) loadItem();}
      } catch {if (!cancelled) setCheckMessage("Health status could not be refreshed. Return to the connection overview to retry.");}
    }
    if (connectionId) void poll();
    return () => {cancelled = true; window.clearTimeout(timer);};
  }, [connectionId,schema,name]);

  if (error) {
    if (error.includes("scanned yet")) {
      return (
        <EmptyState
          title="This item hasn't been checked yet"
          action={
            <Link to={`/connections/${connectionId}/overview`} className="button-primary-dark"><Ico t="Go to Overview and run a check" /></Link>
          }
        >
          Run a check from the Overview so Tarsier can read this item's details.
        </EmptyState>
      );
    }
    return <ErrorState message={error} onRetry={loadItem} />;
  }
  if (!item) {
    return <LoadingState label="Loading item" />;
  }

  if (item.readable === false) {
    return <EmptyState title="no permission">This role cannot read this table. Ask the database owner for SELECT access.</EmptyState>;
  }

  const showStatistics = item.kind !== "raster";
  const showQuality = item.kind !== "raster";
  const showHistory = item.kind !== "raster";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-5)", marginBottom: "var(--space-7)", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          <div style={{ marginBottom: "var(--space-3)" }}>
            <StatusBadge kind="info" label={KIND_LABEL[item.kind] ?? item.kind} />
          </div>
          <h1 className="t-display-xl" style={{ margin: 0, overflowWrap: "anywhere" }}>{item.name}</h1>
        </div>
        <HealthRing isSample={item.health_is_sample} score={item.health_score} components={item.health_components} />
        <Link
          to={`/connections/${connectionId}/graph?${new URLSearchParams({ schema: item.schema, name: item.name })}`}
          className="button-secondary-outline"
        ><Ico t="View in Relationship Graph" /></Link>
      </div>

      <div role="group" aria-label="Sections" style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-7)", flexWrap: "wrap" }}>
        <TabButton active={tab === "overview"} onClick={() => setTab("overview")}>Overview</TabButton>
        {showStatistics && (
          <TabButton active={tab === "statistics"} onClick={() => setTab("statistics")}>Statistics</TabButton>
        )}
        {showQuality && (
          <TabButton active={tab === "quality"} onClick={() => setTab("quality")}>Quality</TabButton>
        )}
        {showHistory && (
          <TabButton active={tab === "history"} onClick={() => setTab("history")}>History</TabButton>
        )}
        <TabButton active={tab === "connections"} onClick={() => setTab("connections")}>Connections</TabButton>
      </div>

      {checkMessage && <p role="status" className="card t-caption">{checkMessage}</p>}
      {!checkMessage && item.health_score == null && <p className="t-caption">{checkFinished ? "The check finished, but this layer has no applicable health components. See Quality for availability details." : <>Health checks have not produced a score for this layer yet. <Link to={`/connections/${connectionId}/overview`}>Run a full health check from the connection overview.</Link></>}</p>}
      {tab === "overview" && <OverviewPanel item={item} connectionId={connectionId!} />}
      {tab === "overview" && item.kind === "tabular" && connectionId && (
        <TabularPanel connectionId={connectionId} item={item} />
      )}
      {tab === "overview" && item.kind === "raster" && connectionId && (
        <RasterPanel connectionId={connectionId} item={item} />
      )}
      {tab === "statistics" && showStatistics && connectionId && (
        <StatisticsPanel key={`${connectionId}:${item.schema}:${item.name}`} connectionId={connectionId} item={item} initialFlag={requestedFlag} />
      )}
      {tab === "quality" && showQuality && connectionId && (
        <QualityPanel key={`${connectionId}:${item.schema}:${item.name}`} connectionId={connectionId} item={item} onChecked={loadItem} />
      )}
      {tab === "connections" && connectionId && <ConnectionsPanel connectionId={connectionId} item={item} />}
      {tab === "history" && showHistory && connectionId && (
        <HistoryPanel connectionId={connectionId} item={item} />
      )}
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        background: active ? "var(--primary)" : "transparent",
        color: active ? "var(--on-primary)" : "var(--ink-body)",
        border: `1px solid ${active ? "var(--primary)" : "transparent"}`,
        borderRadius: "var(--radius-pill)",
        padding: "10px 20px",
        fontFamily: "inherit",
        fontSize: 15,
        fontWeight: 500,
        cursor: "pointer",
        minHeight: 40,
      }}
    >
      {children}
    </button>
  );
}

function OverviewPanel({ item, connectionId }: { item: CachedItem; connectionId: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: item.kind !== "tabular" ? "1fr 1fr" : "1fr", gap: "var(--space-6)" }}>
      <div className="card">
        <h2 className="t-display-sm" style={{ marginBottom: "var(--space-5)" }}>Overview</h2>
        <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--space-4) var(--space-6)", margin: 0 }}>
          <dt className="t-caption">Rows / features</dt>
          <dd>{formatRowCount(item.row_count, item.row_count_is_estimate, item.row_count_is_capped)}</dd>
          <dt className="t-caption">Size</dt>
          <dd>{formatBytes(item.size_bytes)}</dd>
          {item.kind === "vector" && (
            <>
              <dt className="t-caption">Geometry type</dt>
              <dd>{item.geometry_type ?? "Not available"}</dd>
              <dt className="t-caption">Projection</dt>
              <dd>{item.srid ? `EPSG:${item.srid}` : "Not available"}</dd>
              <dt className="t-caption">Index</dt>
              <dd>{item.has_index === null ? "Not available" : item.has_index ? "Yes" : "No"}</dd>
            </>
          )}
          {item.kind === "raster" && (
            <>
              <dt className="t-caption">Dimensions</dt>
              <dd>{item.raster_width && item.raster_height ? `${item.raster_width} × ${item.raster_height} px` : "Not available"}</dd>
              <dt className="t-caption">Bands</dt>
              <dd>{item.raster_band_count ?? "Not available"}</dd>
              <dt className="t-caption">Data type</dt>
              <dd>{item.raster_dtype ?? "Not available"}</dd>
              <dt className="t-caption">Nodata value</dt>
              <dd>{item.raster_nodata ?? "Not available"}</dd>
              <dt className="t-caption">Projection</dt>
              <dd>{item.srid ? `EPSG:${item.srid}` : "Not available"}</dd>
            </>
          )}
          <dt className="t-caption">Last changed</dt>
          <dd>{item.last_modified ? formatDate(item.last_modified) : "Not tracked yet"}</dd>
          <dt className="t-caption">Last scanned</dt>
          <dd>{formatDate(item.scanned_at)}</dd>
        </dl>
      </div>

      {item.kind !== "tabular" && (
        <div className="card">
          <h2 className="t-heading-lg" style={{ marginTop: 0 }}>Map preview</h2>
          {item.kind === "vector" ? <LayerMap connectionId={connectionId} item={item} /> : <MapPreview bbox={item.bbox} height={260} />}
        </div>
      )}
    </div>
  );
}

function LayerMap({connectionId, item}: {connectionId: string; item: CachedItem}) {
  const [preview, setPreview] = useState<{geojson: FeatureCollection; bbox: [number,number,number,number] | null; feature_count: number; is_sample: boolean} | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(""); setPreview(null);
    fetch(`/api/connections/${connectionId}/item/map?${new URLSearchParams({schema:item.schema,name:item.name})}`, {signal:controller.signal})
      .then(r => r.status === 404 ? fetch(`/api/connections/${connectionId}/item/map/scan?${new URLSearchParams({schema:item.schema,name:item.name})}`, {method:"POST",signal:controller.signal}) : r)
      .then(async r => {const body = await r.json(); if (!r.ok) throw Error(body.detail); if (!body.geojson) throw Error("Map geometry is not available for this layer."); return body;})
      .then(setPreview).catch(e => {if(e.name !== "AbortError") setError(e.message);});
    return () => controller.abort();
  }, [connectionId,item.schema,item.name,attempt]);
  if (error) return <div role="status"><p className="t-caption">{error}</p><button className="button-secondary-outline" onClick={() => setAttempt(a=>a+1)}><Ico t="Retry map preview" /></button></div>;
  if (!preview) return <p role="status" className="t-caption">Loading map geometry…</p>;
  return <><MapPreview bbox={preview.bbox} geometry={preview.geojson} height={260} /><p className="t-caption">{preview.feature_count} features shown{preview.is_sample ? " from a sample" : ""}. Map coordinates: WGS84.</p></>;
}

export default ItemDetail;
