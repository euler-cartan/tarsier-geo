import { Ico } from "../components/Icon";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  getGraphNeighborhood,
  getGraphOverview,
  getGraphPath,
  getGraphStatus,
  GraphItem,
  GraphNeighborhood,
  GraphOverview,
  GraphPath,
} from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import { palette } from "../design";
import Flowchart from "./Flowchart";

const itemKey = (item: { connection_id: string; schema: string; name: string }) =>
  `${item.connection_id}|${item.schema}|${item.name}`;

const label = (item: GraphItem) => `${item.name}${item.connection_name ? ` (${item.connection_name})` : ""}`;

function itemUrl(item: { connection_id: string; schema: string; name: string }) {
  return `/connections/${item.connection_id}/items?${new URLSearchParams({ schema: item.schema, name: item.name })}`;
}

/** FSD 12.1 - Relationship Graph (PRD 14.1): neighbourhood, shortest path and connected groups. */
function RelationshipGraph() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const [available, setAvailable] = useState<{ ok: boolean; message: string | null } | null>(null);
  const [overview, setOverview] = useState<GraphOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [start, setStart] = useState<string>(() =>
    searchParams.get("name") && connectionId
      ? `${connectionId}|${searchParams.get("schema") ?? ""}|${searchParams.get("name")}`
      : ""
  );
  const [hops, setHops] = useState(2);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [hood, setHood] = useState<GraphNeighborhood | null>(null);
  const [hoodError, setHoodError] = useState<string | null>(null);
  const [pathTarget, setPathTarget] = useState("");
  const [path, setPath] = useState<GraphPath | null | undefined>(undefined);

  const loadOverview = useCallback(async () => {
    setError(null);
    try {
      const status = await getGraphStatus();
      setAvailable({ ok: status.available, message: status.message });
      if (!status.available) return;
      setOverview(await getGraphOverview(confirmedOnly));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the relationship graph.");
    }
  }, [confirmedOnly]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const items = overview?.all_items ?? [];
  const byKey = useMemo(() => new Map(items.map((i) => [itemKey(i), i])), [items]);

  // Default to the first connected item when the user didn't arrive from one.
  useEffect(() => {
    if (!overview || start) return;
    const firstGroup = overview.groups[0]?.items[0];
    if (firstGroup) setStart(itemKey(firstGroup));
  }, [overview, start]);

  useEffect(() => {
    const item = byKey.get(start);
    if (!start || !item) {
      setHood(null);
      return;
    }
    setHoodError(null);
    getGraphNeighborhood(item.connection_id, item.schema, item.name, hops, confirmedOnly)
      .then(setHood)
      .catch((err) => setHoodError(err instanceof Error ? err.message : "Could not load this item's neighbourhood."));
  }, [start, hops, confirmedOnly, byKey]);

  useEffect(() => {
    const from = byKey.get(start);
    const to = byKey.get(pathTarget);
    if (!from || !to || start === pathTarget) {
      setPath(undefined);
      return;
    }
    getGraphPath(from, to, confirmedOnly)
      .then((result) => setPath(result.path))
      .catch(() => setPath(undefined));
  }, [start, pathTarget, confirmedOnly, byKey]);

  // Draw: neighbourhood, with the active shortest path laid over it.
  useEffect(() => {
    const container = canvasRef.current;
    if (!container || !hood || !hood.found) return;
    const elements: ElementDefinition[] = [];
    const seen = new Set<string>();
    const addNode = (node: GraphItem & { degree?: number; distance?: number }, onPath = false) => {
      const key = itemKey(node);
      if (seen.has(key)) return;
      seen.add(key);
      const degree = node.degree ?? 0;
      elements.push({
        data: {
          id: key,
          label: `${node.name}\n${node.connection_name ?? ""}`,
          kind: node.kind,
          size: 56 + Math.min(degree, 6) * 6, // most-connected items are a little larger
          start: key === start,
          item: node,
        },
        classes: onPath ? "on-path" : "",
      });
    };
    hood.nodes.forEach((n) => addNode(n));
    (path?.items ?? []).forEach((n) => addNode({ ...n, connection_name: byKey.get(itemKey(n))?.connection_name }, true));
    hood.edges.forEach((e, i) =>
      elements.push({
        data: {
          id: `e${i}`, source: e.source, target: e.target, kind: e.kind, status: e.status,
          label: e.source_column === e.target_column ? e.source_column : `${e.source_column} ↔ ${e.target_column}`,
        },
      })
    );
    (path?.items ?? []).slice(1).forEach((to, i) => {
      const from = path!.items[i];
      const step = path!.links[i];
      elements.push({
        data: {
          id: `p${i}`, source: itemKey(from), target: itemKey(to), kind: step.kind, status: step.status,
          label: step.source_column === step.target_column ? step.source_column : `${step.source_column} ↔ ${step.target_column}`,
        },
        classes: "on-path",
      });
    });

    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.25,
      maxZoom: 2.5,
      wheelSensitivity: 0.36,
      style: [
        { selector: "node", style: {
          label: "data(label)", color: palette.ink, "font-size": 11, "font-weight": 500, "text-wrap": "wrap",
          "text-max-width": "130px", "text-valign": "center", "text-halign": "center", "background-color": palette.card,
          "border-width": 2, "border-color": palette.hairlineStrong, shape: "round-rectangle", width: 150, height: "data(size)",
        } },
        { selector: "node[?start]", style: { "border-width": 4, "border-color": palette.primary } },
        { selector: "edge", style: {
          width: 2, "line-color": palette.faint, "target-arrow-color": palette.faint, "target-arrow-shape": "triangle",
          "curve-style": "bezier", label: "data(label)", color: palette.muted, "font-size": 10,
          "text-background-color": palette.canvas, "text-background-opacity": 1, "text-background-padding": "3px",
          "text-rotation": "autorotate",
        } },
        { selector: "edge[status = 'guessed']", style: { "line-style": "dashed", "line-color": palette.warning, "target-arrow-color": palette.warning } },
        { selector: "node.on-path", style: { "border-color": palette.primary, "border-width": 4, "background-color": palette.surfaceStrong } },
        { selector: "edge.on-path", style: { width: 5, "line-color": palette.primary, "target-arrow-color": palette.primary } },
      ],
      layout: { name: "cose", animate: false, fit: true, padding: 45, nodeRepulsion: () => 9000, idealEdgeLength: () => 190 },
    });
    cyRef.current = cy;
    cy.on("tap", "node", (event) => navigate(itemUrl(event.target.data("item"))));
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [hood, path, start, byKey, navigate]);

  if (error) return <ErrorState message={error} onRetry={() => void loadOverview()} />;
  if (!available) return <LoadingState label="Loading the relationship graph" />;

  const flowchartLink = (
    <Link to={`/connections/${connectionId}/flowchart`} className="button-secondary-outline"><Ico t="Back to the connection flowchart" /></Link>
  );

  if (!available.ok) {
    return <><p className="t-caption" role="status">Showing the connection graph. Advanced path queries are unavailable on this Python version.</p><Flowchart /></>;
  }
  if (!overview) return <LoadingState label="Loading the relationship graph" />;

  if (overview.all_items.length === 0) {
    return (
      <div>
        <h1 className="t-display-lg">Relationship Graph</h1>
        <EmptyState title="Nothing to show yet" action={flowchartLink}>
          Run a check on a connection so Tarsier knows its items, then scan the flowchart to find how they connect.
        </EmptyState>
      </div>
    );
  }

  const startItem = byKey.get(start);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <h1 className="t-display-lg" style={{ margin: 0 }}>Relationship Graph</h1>
        {flowchartLink}
      </div>

      <div style={{ display: "flex", gap: "var(--space-6)", marginTop: "var(--space-5)", alignItems: "flex-start" }}>
        <aside style={{ width: 320, flexShrink: 0, display: "grid", gap: "var(--space-5)" }} aria-label="Graph controls">
          <section className="card">
            <label className="t-caption" style={{ display: "block" }}>
              Start from
              <select className="text-input" style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }}
                value={start} onChange={(e) => { setStart(e.target.value); setPathTarget(""); }}>
                <option value="">Choose an item</option>
                {items.map((i) => <option key={itemKey(i)} value={itemKey(i)}>{label(i)}</option>)}
              </select>
            </label>

            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              <span className="t-caption" id="hops-label">Reachable within</span>
              <button type="button" className="button-secondary-outline" aria-label="Fewer links" disabled={hops <= 1} onClick={() => setHops(hops - 1)}><Ico t="−" /></button>
              <output aria-labelledby="hops-label">{hops}</output>
              <button type="button" className="button-secondary-outline" aria-label="More links" disabled={hops >= 6} onClick={() => setHops(hops + 1)}><Ico t="+" /></button>
              <span className="t-caption">links</span>
            </div>

            <label className="t-caption" style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", marginTop: "var(--space-4)", minHeight: 40 }}>
              <input type="checkbox" checked={confirmedOnly} onChange={(e) => setConfirmedOnly(e.target.checked)} />
              Confirmed links only
            </label>
          </section>

          <section className="card">
            <h2 className="t-heading-lg" style={{ marginTop: 0 }}>Shortest path</h2>
            <label className="t-caption" style={{ display: "block" }}>
              To
              <select className="text-input" style={{ display: "block", width: "100%", marginTop: "var(--space-2)" }}
                value={pathTarget} onChange={(e) => setPathTarget(e.target.value)} disabled={!startItem}>
                <option value="">Choose a second item</option>
                {items.filter((i) => itemKey(i) !== start).map((i) => <option key={itemKey(i)} value={itemKey(i)}>{label(i)}</option>)}
              </select>
            </label>
            {pathTarget && path === null && (
              <p className="t-caption" role="status">These two items aren't connected{confirmedOnly ? " by confirmed links" : ""}.</p>
            )}
            {path && (
              <ol aria-label="Path" style={{ paddingLeft: "var(--space-5)" }}>
                {path.items.map((item, i) => (
                  <li key={itemKey(item)}>
                    {item.name}
                    {path.links[i] && (
                      <div className="t-caption">
                        via {path.links[i].source_column === path.links[i].target_column
                          ? path.links[i].source_column
                          : `${path.links[i].source_column} ↔ ${path.links[i].target_column}`}
                        {path.links[i].status === "guessed" ? " (guessed)" : ""}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section className="card">
            <h2 className="t-heading-lg" style={{ marginTop: 0 }}>Connected groups</h2>
            {overview.groups.length === 0 ? (
              <p className="t-caption">No items are connected yet{confirmedOnly ? " by confirmed links" : ""}.</p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "var(--space-3)" }}>
                {overview.groups.map((group, index) => (
                  <li key={index}>
                    <button
                      type="button"
                      className="button-secondary-outline"
                      style={{ width: "100%", textAlign: "left" }}
                      onClick={() => { setStart(itemKey(group.items[0])); setPathTarget(""); }}
                    >
                      {group.size} items{group.spans_connections ? " · crosses connections" : ""}
                    </button>
                    <div className="t-caption">{group.items.map((i) => i.name).join(", ")}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>

        <div style={{ flex: 1, minWidth: 0 }}>
          {hoodError && <ErrorState message={hoodError} />}
          {!startItem && (
            <EmptyState title="Choose an item to begin">Pick a starting item on the left to see what it is connected to.</EmptyState>
          )}
          {startItem && hood && !hood.found && (
            <EmptyState title="That item isn't in the graph yet">Run a check on its connection, then scan the flowchart.</EmptyState>
          )}
          {startItem && hood?.found && (
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div ref={canvasRef} aria-label="Relationship graph canvas" style={{ width: "100%", height: 560, background: "var(--canvas-soft)" }} />
              <div className="t-caption" style={{ display: "flex", gap: 18, flexWrap: "wrap", padding: "var(--space-3) var(--space-4)" }}>
                <span>Solid line: confirmed</span>
                <span style={{ color: "var(--status-warning)" }}>Dashed line: guessed</span>
                <span>Heavy dark line: shortest path</span>
                <span>Larger box: more links</span>
                <span>Click an item to open it</span>
              </div>
              {hood.nodes.length === 1 && (
                <p className="t-caption" style={{ padding: "0 var(--space-4) var(--space-4)" }}>
                  {startItem.name} has no links{confirmedOnly ? " that are confirmed" : ""}.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default RelationshipGraph;
