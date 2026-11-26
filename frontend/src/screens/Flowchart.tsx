import { Ico } from "../components/Icon";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  addFlowchartLink,
  FlowchartLink,
  FlowchartNode,
  FlowchartPayload,
  getFlowchart,
  scanCrossConnectionLinks,
  scanFlowchart,
  updateGuessedLink,
} from "../api";
import { palette } from "../design";

const KIND_LABEL: Record<FlowchartNode["kind"], string> = {
  vector: "Vector", raster: "Raster", tabular: "Table",
};

function nodeId(node: Pick<FlowchartNode, "schema" | "name">) {
  return JSON.stringify([node.schema, node.name]);
}

/** Items in another connection get their own id space so equal names never collide. */
function externalId(connectionId: string, node: Pick<FlowchartNode, "schema" | "name">) {
  return JSON.stringify(["ext", connectionId, node.schema, node.name]);
}

function nodeLabel(node: FlowchartNode) {
  const type = node.kind === "vector" ? "V" : node.kind === "raster" ? "R" : "T";
  const where = node.connection_name ? `\n${node.connection_name}` : node.schema ? `\n${node.schema}` : "";
  return `${type}  ${node.name}${where}`;
}

function edgeLabel(link: FlowchartLink) {
  const columns = link.source_column === link.target_column
    ? link.source_column
    : `${link.source_column} ↔ ${link.target_column}`;
  if (link.kind === "guessed" && link.status === "guessed") return `? ${columns}${link.sample_based ? " · sample" : ""}`;
  if (link.kind === "user") return `♟ ${columns}`;
  return columns;
}

function typeBadge(fill: string, letter: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="18"><rect width="24" height="18" rx="4" fill="${fill}"/><text x="12" y="13" text-anchor="middle" font-family="Arial,sans-serif" font-size="11" font-weight="700" fill="white">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function Flowchart() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const focusName = searchParams.get("name"), focusSchema = searchParams.get("schema") || "";
  const focusScan = useRef(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [graph, setGraph] = useState<FlowchartPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crossNote, setCrossNote] = useState<string | null>(null);
  const [unverifiedCount, setUnverifiedCount] = useState(0);
  const [selectedNode, setSelectedNode] = useState<FlowchartNode | null>(null);
  const [selectedLink, setSelectedLink] = useState<FlowchartLink | null>(null);
  const [selectedGuess, setSelectedGuess] = useState<FlowchartLink | null>(null);
  const [highlightLinkIds, setHighlightLinkIds] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [adding, setAdding] = useState(false);
  const [sourceKey, setSourceKey] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const [sourceColumn, setSourceColumn] = useState("");
  const [targetColumn, setTargetColumn] = useState("");
  const [savingLink, setSavingLink] = useState(false);

  const nodeByKey = useMemo(() => new Map((graph?.nodes ?? []).map((node) => [nodeId(node), node])), [graph]);
  const sourceNode = nodeByKey.get(sourceKey);
  const targetNode = nodeByKey.get(targetKey);

  const load = useCallback(async () => {
    if (!connectionId) return;
    setLoading(true);
    setError(null);
    try {
      let result = await getFlowchart(connectionId);
      if (focusName && !result.nodes.length && !focusScan.current) {focusScan.current = true; result = await scanFlowchart(connectionId);}
      setGraph(result);
      if (result.could_not_verify !== undefined) {
        setUnverifiedCount(result.could_not_verify);
        setCrossNote(result.message ?? null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the connection flowchart.");
    } finally {
      setLoading(false);
    }
  }, [connectionId, focusName]);

  useEffect(() => { void load(); }, [load]);

  async function scanOtherConnections() {
    if (!connectionId) return;
    setScanning(true);
    setError(null);
    setCrossNote(null);
    try {
      const result = await scanCrossConnectionLinks();
      setUnverifiedCount(result.could_not_verify ?? 0);
      setCrossNote(
        `${result.guesses} possible connection${result.guesses === 1 ? "" : "s"} found between your data sources.` +
          (result.skipped_connections.length ? ` Could not read: ${result.skipped_connections.join(", ")}.` : "") +
          (result.message ? ` ${result.message}` : "")
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not compare your connections.");
    } finally {
      setScanning(false);
    }
  }

  async function scan() {
    if (!connectionId) return;
    setScanning(true);
    setError(null);
    try {
      const result = await scanFlowchart(connectionId);
      setUnverifiedCount(result.could_not_verify ?? 0);
      setCrossNote(result.message ?? null);
      setHighlightLinkIds(result.links.filter((link) => link.kind === "guessed" && link.status === "guessed").map((link) => link.id));
      setGraph(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not scan connections.");
    } finally {
      setScanning(false);
    }
  }

  useEffect(() => {
    const container = canvasRef.current;
    if (!container || !graph || graph.nodes.length === 0 || !connectionId) return;
    const layoutKey = `tarsier-flowchart-layout-${connectionId}`;
    let saved: Record<string, { x: number; y: number }> = {};
    try { saved = JSON.parse(sessionStorage.getItem(layoutKey) ?? "{}"); } catch { /* ignored */ }
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((node, index) => ({
        data: { id: nodeId(node), label: nodeLabel(node), kind: node.kind, item: node },
        position: saved[nodeId(node)] ?? { x: 170 + (index % 3) * 230, y: 100 + Math.floor(index / 3) * 150 },
      })),
      ...(graph.external_nodes ?? []).map((node, index) => ({
        data: { id: externalId(node.connection_id ?? "", node), label: nodeLabel(node), kind: node.kind, item: node, external: true },
        position: saved[externalId(node.connection_id ?? "", node)] ?? { x: 170 + (index % 3) * 230, y: 100 + (Math.floor(graph.nodes.length / 3) + 1 + Math.floor(index / 3)) * 150 },
      })),
      ...graph.links.map((link) => ({
        data: {
          id: link.id,
          source: link.source_connection_id && link.source_connection_id !== connectionId
            ? externalId(link.source_connection_id, { schema: link.source_schema, name: link.source_name })
            : nodeId({ schema: link.source_schema, name: link.source_name }),
          target: link.target_connection_id && link.target_connection_id !== connectionId
            ? externalId(link.target_connection_id, { schema: link.target_schema, name: link.target_name })
            : nodeId({ schema: link.target_schema, name: link.target_name }),
          label: edgeLabel(link),
          kind: link.kind,
          pending: link.kind === "guessed" && link.status === "guessed",
          link,
        },
        ...(highlightLinkIds.includes(link.id) && link.kind === "guessed" && link.status === "guessed" ? { classes: "newly-found" } : {}),
      })),
    ];
    const cy = cytoscape({
      container,
      elements,
      minZoom: 0.25,
      maxZoom: 2.5,
      wheelSensitivity: 0.36,
      style: [
        { selector: "node:selected", style: { "border-width": 3, "border-color": palette.ink } },
        { selector: "edge:selected", style: { "line-color": palette.ink, "width": 3 } },
        { selector: "node", style: {
          label: "data(label)", color: palette.ink, "font-size": 12, "font-weight": 500,
          "text-wrap": "wrap", "text-max-width": "150px", "text-valign": "center", "text-halign": "center",
          "background-color": palette.card, "border-width": 2, "border-color": palette.hairlineStrong,
          "border-opacity": 1, width: 190, height: 64, shape: "round-rectangle",
          "text-background-color": palette.card, "text-background-opacity": 0,
          "background-repeat": "no-repeat", "background-position-x": "5px", "background-position-y": "5px",
          "background-width": "24px", "background-height": "18px",
        } },
        { selector: "node[kind = 'vector']", style: { "border-color": palette.sky, "background-image": typeBadge(palette.primary, "V") } },
        { selector: "node[kind = 'raster']", style: { "border-color": palette.mint, "background-image": typeBadge(palette.primary, "R") } },
        { selector: "node[kind = 'tabular']", style: { "border-color": palette.peach, "background-image": typeBadge(palette.primary, "T") } },
        { selector: "node[?external]", style: { "border-style": "dashed", "background-color": palette.surfaceStrong } },
        { selector: "node:active", style: { "overlay-opacity": 0.12, "overlay-color": palette.sky } },
        { selector: "edge", style: {
          width: 2, "line-color": palette.faint, "target-arrow-color": palette.faint, "target-arrow-shape": "triangle",
          "source-arrow-color": palette.faint, "source-arrow-shape": "circle", "source-arrow-fill": "filled", "arrow-scale": 0.9,
          "curve-style": "round-taxi", "taxi-direction": "rightward", label: "data(label)", color: palette.muted, "font-size": 10,
          "text-background-color": palette.canvas, "text-background-opacity": 1, "text-background-padding": "3px",
          "text-rotation": "autorotate", "transition-property": "line-color, width, opacity", "transition-duration": 500,
        } },
        { selector: "edge[kind = 'guessed']", style: { "line-style": "dashed", "line-color": palette.warning, "target-arrow-color": palette.warning, "source-arrow-color": palette.warning } },
        { selector: "edge[kind = 'user']", style: { "line-color": palette.primary, "target-arrow-color": palette.primary, "source-arrow-color": palette.primary } },
        { selector: "edge.newly-found", style: { width: 5, opacity: 0.35, "line-color": palette.sky, "target-arrow-color": palette.sky } },
      ],
      layout: graph.nodes.every((node) => Boolean(saved[nodeId(node)])) && (graph.external_nodes ?? []).every((node) => Boolean(saved[externalId(node.connection_id ?? "", node)]))
        ? { name: "preset", fit: true, padding: 45 }
        : graph.links.length === 0
          ? { name: "grid", fit: true, padding: 45, avoidOverlap: true, spacingFactor: 1.3 } // nothing connected yet: lay items out in a tidy grid
          : { name: "cose", animate: false, fit: true, padding: 45, nodeRepulsion: () => 9000, idealEdgeLength: () => 190 },
    });
    cyRef.current = cy;
    if (focusName) {
      const focused = cy.getElementById(nodeId({schema:focusSchema,name:focusName}));
      if (focused.length) {focused.select(); cy.center(focused); setSelectedNode(focused.data("item"));}
    }
    cy.on("tap", "node", (event) => {
      const item = event.target.data("item") as FlowchartNode;
      setSelectedNode(item); setSelectedLink(null);
    });
    cy.on("tap", "edge", (event) => {
      const link = event.target.data("link") as FlowchartLink;
      setSelectedLink(link); setSelectedNode(null);
      if (link.kind === "guessed" && link.status === "guessed") setSelectedGuess(link);
    });
    cy.on("dragfree", "node", () => {
      const positions: Record<string, { x: number; y: number }> = {};
      cy.nodes().forEach((node) => { positions[node.id()] = node.position(); });
      sessionStorage.setItem(layoutKey, JSON.stringify(positions));
    });
    const highlightTimer = window.setTimeout(() => cy.edges(".newly-found").removeClass("newly-found"), 80);
    return () => { window.clearTimeout(highlightTimer); cy.destroy(); cyRef.current = null; };
  }, [connectionId, graph, highlightLinkIds, navigate, focusName, focusSchema]);

  // While a dialog is open, the page behind it must not scroll.
  const dialogOpen = Boolean(selectedGuess || adding);
  useEffect(() => {
    if (!dialogOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [dialogOpen]);

  async function decideGuess(action: "confirm" | "reject") {
    if (!connectionId || !selectedGuess) return;
    setConfirming(true);
    setError(null);
    try {
      await updateGuessedLink(connectionId, selectedGuess.id, action);
      setSelectedGuess(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update that guessed connection.");
    } finally {
      setConfirming(false);
    }
  }

  function openAddDialog() {
    setSourceKey(""); setTargetKey(""); setSourceColumn(""); setTargetColumn(""); setError(null); setAdding(true);
  }

  async function submitLink(event: FormEvent) {
    event.preventDefault();
    if (!connectionId || !sourceNode || !targetNode) return;
    setSavingLink(true); setError(null);
    try {
      await addFlowchartLink(connectionId, {
        source_schema: sourceNode.schema, source_name: sourceNode.name, source_column: sourceColumn,
        target_schema: targetNode.schema, target_name: targetNode.name, target_column: targetColumn,
      });
      setAdding(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that connection.");
    } finally {
      setSavingLink(false);
    }
  }

  const actions = (
    <div style={{ display: "flex", gap: "var(--space-3)" }}>
      <button className="button-secondary-outline" type="button" onClick={() => void scan()} disabled={scanning || loading}><Ico t={scanning ? "Scanning…" : "Scan connections"} /></button>
      <Link className="button-secondary-outline" to={`/connections/${connectionId}/graph`}><Ico t="Relationship Graph" /></Link>
      <button className="button-secondary-outline" type="button" onClick={() => void scanOtherConnections()} disabled={scanning || loading}><Ico t="Compare with other connections" /></button>
      <button className="button-primary-dark" type="button" onClick={openAddDialog} disabled={!graph?.nodes.length}><Ico t="Add connection" /></button>
    </div>
  );

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="t-heading-xl" style={{ marginTop: 0, marginBottom: 6 }}>Connection flowchart</h1>
          <p className="t-body-md" style={{ color: "var(--ink-mute)", marginTop: 0 }}>Explore items and the columns that connect them.</p>
        </div>
        {actions}
      </div>
      <div className="canvas-toolbar flowchart-toolbar"><span className="t-caption">Select a node or connection to inspect it.</span><div><button type="button" className="button-secondary-outline" onClick={() => cyRef.current?.zoom((cyRef.current?.zoom() || 1) / 1.2)} aria-label="Zoom out"><Ico t="−" /></button> <button type="button" className="button-secondary-outline" onClick={() => cyRef.current?.zoom((cyRef.current?.zoom() || 1) * 1.2)} aria-label="Zoom in"><Ico t="+" /></button> <button type="button" className="button-secondary-outline" onClick={() => cyRef.current?.fit(undefined, 45)}><Ico t="Fit graph" /></button> <button type="button" className="button-secondary-outline" onClick={() => cyRef.current?.layout({name: "breadthfirst", directed: true, padding: 45, spacingFactor: 1.4}).run()}><Ico t="Arrange" /></button></div></div>
      {selectedNode && <div className="graph-inspector card">
        <div><span className="t-label">{KIND_LABEL[selectedNode.kind]}</span><h3>{selectedNode.name}</h3><p className="t-caption">{selectedNode.connection_name || selectedNode.schema || "Current connection"}</p></div>
        <button className="button-primary-dark" onClick={() => navigate(`/connections/${selectedNode.connection_id ?? connectionId}/items?schema=${encodeURIComponent(selectedNode.schema)}&name=${encodeURIComponent(selectedNode.name)}`)}><Ico t="Open details" /></button>
        {(!selectedNode.connection_id || selectedNode.connection_id === connectionId) && <button className="button-secondary-outline" onClick={() => {setSourceKey(nodeId(selectedNode)); setSourceColumn(""); setAdding(true);}}><Ico t="Add relationship" /></button>}
        <button className="button-secondary-outline" onClick={() => setSelectedNode(null)}><Ico t="Close" /></button>
      </div>}
      {selectedLink && <div className="graph-inspector card"><div><span className="t-label">{selectedLink.kind} relationship</span><h3>{selectedLink.source_column} → {selectedLink.target_column}</h3><p className="t-caption">{selectedLink.status}</p></div><button className="button-secondary-outline" onClick={() => setSelectedLink(null)}><Ico t="Close" /></button></div>}
      {crossNote && <p role="status" className="t-caption">{crossNote}</p>}
      {error && (
        <div role="alert" style={{ margin: "var(--space-4) 0" }}>
          <p style={{ color: "var(--status-danger)", margin: "0 0 var(--space-3)" }}>{error}</p>
          <button type="button" className="button-secondary-outline" onClick={() => void load()}><Ico t="Retry" /></button>
        </div>
      )}
      <div className="card" style={{ padding: 0, overflow: "hidden", marginTop: 20 }}>
        {loading || scanning ? (
          <div aria-busy="true" aria-label="Loading connection graph" style={{ minHeight: 560, display: "grid", placeItems: "center", background: "var(--canvas-soft)", backgroundImage: "radial-gradient(var(--hairline-strong) 1px, transparent 1px)", backgroundSize: "20px 20px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(120px, 180px))", gap: 30 }}>
              {[0, 1, 2, 3, 4, 5].map((n) => <div key={n} className="card" style={{ height: 58, opacity: 0.55 }} />)}
            </div>
          </div>
        ) : graph && graph.nodes.length === 0 ? (
          <div style={{ minHeight: 400, display: "grid", placeItems: "center", padding: 32, textAlign: "center" }}>
            <div><h2 className="t-heading-lg">{unverifiedCount ? "Some candidates could not be verified" : "No connections found yet"}</h2><p className="t-body-md">Run a scan to find links or add one manually.</p>{actions}</div>
          </div>
        ) : graph && graph.links.length === 0 ? (
          <>
            <div ref={canvasRef} style={{ width: "100%", height: 560, background: "var(--canvas-soft)", backgroundImage: "radial-gradient(var(--hairline-strong) 1px, transparent 1px)", backgroundSize: "20px 20px" }} />
            <p className="t-caption" style={{ padding: "0 20px 16px" }}>{unverifiedCount ? "Some candidates could not be verified. No conclusion about those links was made." : "No connections found yet  -  run a scan or add one manually."}</p>
          </>
        ) : (
          <div ref={canvasRef} aria-label="Interactive connection graph" style={{ width: "100%", height: 560, background: "var(--canvas-soft)", backgroundImage: "radial-gradient(var(--hairline-strong) 1px, transparent 1px)", backgroundSize: "20px 20px" }} />
        )}
      </div>
      {graph && !loading && !scanning && (
        <div className="t-caption" style={{ display: "flex", gap: 18, flexWrap: "wrap", marginTop: 12 }}>
          <span>Solid line: confirmed</span><span style={{ color: "var(--status-warning)" }}>Dashed line + ?: guessed, please confirm</span><span style={{ color: "#267447" }}>♟: added by you</span>
          <span>Dashed box: item in another connection</span><span>V: vector · R: raster · T: table</span><span>Drag nodes to rearrange · drag blank space to pan · scroll to zoom</span>
        </div>
      )}

      {selectedGuess && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !confirming) setSelectedGuess(null); }}>
          <div role="dialog" aria-modal="true" aria-labelledby="guess-title" className="modal-panel">
            <h2 id="guess-title" className="t-heading-lg">Confirm this guessed connection?</h2>
            <p className="t-body-md">{selectedGuess.source_name}.{selectedGuess.source_column} ↔ {selectedGuess.target_name}.{selectedGuess.target_column}</p>
            {selectedGuess.sample_based && <p className="modal-hint">This guess is based on sampled values.</p>}
            <div className="modal-actions">
              <button className="button-secondary-outline" onClick={() => void decideGuess("reject")} disabled={confirming}><Ico t="Reject" /></button>
              <button className="button-primary-dark" onClick={() => void decideGuess("confirm")} disabled={confirming}><Ico t={confirming ? "Saving…" : "Confirm"} /></button>
            </div>
            <button type="button" className="modal-close" aria-label="Close" onClick={() => setSelectedGuess(null)}><Ico t="×" /></button>
          </div>
        </div>
      )}

      {adding && graph && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !savingLink) setAdding(false); }}>
          <div role="dialog" aria-modal="true" aria-labelledby="add-link-title" className="modal-panel connect-dialog">
            <h2 id="add-link-title" className="t-heading-lg">Connect items</h2>
            <p className="modal-hint">Pick two items and the column they share.</p>
            <form onSubmit={(event) => void submitLink(event)} className="modal-form">
              <label>First item
                <select className="text-input" value={sourceKey} onChange={(event) => { setSourceKey(event.target.value); setSourceColumn(""); }} required>
                  <option value="">Choose an item</option>{graph.nodes.map((node) => <option key={nodeId(node)} value={nodeId(node)}>{node.schema ? `${node.schema}.` : ""}{node.name} ({KIND_LABEL[node.kind]})</option>)}
                </select>
              </label>
              <label>Joining column
                <select className="text-input" value={sourceColumn} onChange={(event) => setSourceColumn(event.target.value)} required disabled={!sourceNode?.columns.length}>
                  <option value="">Choose a column</option>{sourceNode?.columns.map((column) => <option key={column}>{column}</option>)}
                </select>
              </label>
              <label>Second item
                <select className="text-input" value={targetKey} onChange={(event) => { setTargetKey(event.target.value); setTargetColumn(""); }} required>
                  <option value="">Choose an item</option>{graph.nodes.filter((node) => nodeId(node) !== sourceKey).map((node) => <option key={nodeId(node)} value={nodeId(node)}>{node.schema ? `${node.schema}.` : ""}{node.name} ({KIND_LABEL[node.kind]})</option>)}
                </select>
              </label>
              <label>Joining column
                <select className="text-input" value={targetColumn} onChange={(event) => setTargetColumn(event.target.value)} required disabled={!targetNode?.columns.length}>
                  <option value="">Choose a column</option>{targetNode?.columns.map((column) => <option key={column}>{column}</option>)}
                </select>
              </label>
              {(!sourceNode?.columns.length || !targetNode?.columns.length) && <p className="modal-hint">Column choices are available after a scan for a connector that can sample its data.</p>}
              {error && <p role="alert" className="modal-error">{error}</p>}
              <div className="modal-actions">
                <button className="button-secondary-outline" type="button" onClick={() => setAdding(false)}><Ico t="Cancel" /></button>
                <button className="button-primary-dark" type="submit" disabled={savingLink || !sourceColumn || !targetColumn}><Ico t={savingLink ? "Adding…" : "Add connection"} /></button>
              </div>
            </form>
            <button type="button" className="modal-close" aria-label="Close" onClick={() => setAdding(false)}><Ico t="×" /></button>
          </div>
        </div>
      )}
    </section>
  );
}

export default Flowchart;
