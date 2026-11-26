import { Ico } from "./Icon";
import { ReactNode, useRef, useState } from "react";
import type { AutoGraph, AutoNode, AutoRun } from "../api";

type Props = {graph: AutoGraph; onChange: (graph: AutoGraph) => void; labels: {id: string; label: string; role?: AutoNode["role"]; description?: string}[]; trace: AutoRun["trace"]; glow: string | null; renderConfig: (node: AutoNode) => ReactNode};
const position = (node: AutoNode, index: number) => node.position || {x: 48 + index * 260, y: 120};

export default function WorkflowCanvas({graph, onChange, labels, trace, glow, renderConfig}: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<number | null>(null);
  const [source, setSource] = useState<{id: string; branch: "true" | "false"} | null>(null);
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(1);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{id: string; x: number; y: number; startX: number; startY: number} | null>(null);
  const pan = useRef<{x: number; y: number; left: number; top: number} | null>(null);
  const node = graph.nodes.find(n => n.id === selected);
  const edge = selectedEdge === null ? null : graph.edges[selectedEdge];
  const label = (n: AutoNode) => labels.find(l => l.id === n.kind)?.label || n.kind;
  const width = Math.max(1000, ...graph.nodes.map((n, i) => position(n, i).x + 280));
  const height = Math.max(480, ...graph.nodes.map((n, i) => position(n, i).y + 180));

  function connect(to: string) {
    if (!source) return;
    if (source.id === to || graph.nodes.find(n => n.id === to)?.role === "trigger") { setError("Choose a condition or action as the destination."); return; }
    const reaches = (id: string, seen = new Set<string>()): boolean => {
      if (id === source.id) return true;
      if (seen.has(id)) return false;
      seen.add(id);
      return graph.edges.filter(e => e.from === id).some(e => reaches(e.to, seen));
    };
    if (reaches(to)) { setError("This connection would create a cycle."); return; }
    if (graph.edges.some(e => e.from === source.id && e.to === to && (e.branch || "true") === source.branch)) { setError("These ports are already connected."); return; }
    onChange({...graph, edges: [...graph.edges, {from: source.id, to, branch: source.branch}]});
    setSource(null); setTarget(""); setError("");
  }
  function removeNode() {
    if (!node) return;
    onChange({nodes: graph.nodes.filter(n => n.id !== node.id), edges: graph.edges.filter(e => e.from !== node.id && e.to !== node.id)});
    setSelected(null); setSource(null);
  }
  function insertNode(kind: string) {
    if (!edge || !kind) return;
    const before = graph.nodes.findIndex(n => n.id === edge.from);
    const after = graph.nodes.findIndex(n => n.id === edge.to);
    const p = position(graph.nodes[before], before), q = position(graph.nodes[after], after);
    const id = `insert-${crypto.randomUUID()}`;
    const role: AutoNode["role"] = labels.find(l => l.id === kind)?.role || (["user_eq", "count_drop", "layer_eq", "value_out_of_range"].includes(kind) ? "condition" : "action");
    const inserted: AutoNode = {id, kind, role, config: kind === "run_quality" ? {continue_on_pass: true} : {}, position: {x: (p.x + q.x) / 2, y: p.y + 180}};
    onChange({nodes: [...graph.nodes, inserted], edges: [...graph.edges.filter((_, i) => i !== selectedEdge), {...edge, to: id}, {from: id, to: edge.to}]});
    setSelected(id); setSelectedEdge(null);
  }
  return <div className="workflow-editor">
    <div className="canvas-toolbar"><span className="t-caption">Drag nodes to arrange · Select an output, then an input to connect</span><div><button type="button" className="button-secondary-outline" aria-label="Zoom out" onClick={() => setZoom(z => Math.max(.4, z - .15))}><Ico t="−" /></button><span className="t-caption"> {Math.round(zoom * 100)}% </span><button type="button" className="button-secondary-outline" aria-label="Zoom in" onClick={() => setZoom(z => Math.min(1.8, z + .15))}><Ico t="+" /></button> <button type="button" className="button-secondary-outline" onClick={() => { setZoom(Math.min(1, (viewport.current?.clientWidth || 900) / width)); viewport.current?.scrollTo?.(0, 0); }}><Ico t="Fit" /></button> <button type="button" className="button-secondary-outline" onClick={() => onChange({...graph, nodes: graph.nodes.map((n, i) => ({...n, position: {x: 48 + i * 260, y: 120}}))})}><Ico t="Arrange" /></button></div></div>
    {source && <div className="connection-hint" role="status">Connecting {source.branch} output. Select a destination input. <button type="button" onClick={() => setSource(null)}><Ico t="Cancel" /></button></div>}
    {error && <p role="alert">{error}</p>}
    <div className="workflow-workspace">
      <div ref={viewport} className="workflow-viewport" onPointerDown={e => {if ((e.target as HTMLElement).closest("button, [role=button], .workflow-node")) return; pan.current = {x: e.clientX, y: e.clientY, left: e.currentTarget.scrollLeft, top: e.currentTarget.scrollTop}; e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e => {if (pan.current) {e.currentTarget.scrollLeft = pan.current.left - e.clientX + pan.current.x; e.currentTarget.scrollTop = pan.current.top - e.clientY + pan.current.y;}}} onPointerUp={() => {pan.current = null;}}>
        <div style={{width: width * zoom, height: height * zoom}}><div className="workflow-surface" style={{width, height, transform: `scale(${zoom})`, transformOrigin: "0 0"}}>
          <svg className="workflow-wires" width={width} height={height} aria-label="Workflow connections">
            <defs><marker id="workflow-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
            {graph.edges.map((edge, index) => {
              const a = graph.nodes.findIndex(n => n.id === edge.from), b = graph.nodes.findIndex(n => n.id === edge.to);
              if (a < 0 || b < 0) return null;
              const p = position(graph.nodes[a], a), q = position(graph.nodes[b], b);
              const x = p.x + 196, y = p.y + (edge.branch === "false" ? 94 : 58), endY = q.y + 58;
              const bend = Math.max(60, Math.abs(q.x - x) / 2);
              const passed = trace.some(s => s.node_id === edge.from && (graph.nodes[a].role === "condition" ? s.ok === (edge.branch !== "false") : s.ok)) && trace.some(s => s.node_id === edge.to);
              const path = `M${x},${y} C${x+bend},${y} ${q.x-bend},${endY} ${q.x},${endY}`;
              return <g key={index} className={passed ? "wire executed" : "wire"}><path className="wire-hit" d={path} role="button" tabIndex={0} aria-label={`Connection ${edge.from} to ${edge.to}`} onClick={() => {setSelectedEdge(index); setSelected(null);}} onKeyDown={e => {if (e.key === "Enter" || e.key === " ") {e.preventDefault(); setSelectedEdge(index); setSelected(null);}}} /><path d={path} markerEnd="url(#workflow-arrow)" /><text x={(x+q.x)/2} y={(y+endY)/2-9}>{graph.nodes[a].role === "condition" ? edge.branch || "true" : ""}</text></g>;
            })}
          </svg>
          {!graph.nodes.length && <p className="canvas-empty">Add a trigger to start your workflow.</p>}
          {graph.nodes.map((n, i) => {
            const pos = position(n, i), result = trace.find(s => s.node_id === n.id);
            return <div key={n.id} className={`workflow-node ${n.role} ${selected === n.id ? "selected" : ""} ${glow === n.id ? "running" : ""}`} style={{left: pos.x, top: pos.y}}>
              {n.role !== "trigger" && <button type="button" className="node-port input" title="Connect input" aria-label={`Input of ${label(n)}`} onClick={() => connect(n.id)} />}
              <button type="button" className="node-body" onClick={() => {setSelected(n.id); setSelectedEdge(null);}} onPointerDown={e => {drag.current = {id:n.id, x:pos.x, y:pos.y, startX:e.clientX, startY:e.clientY}; e.currentTarget.setPointerCapture(e.pointerId); e.stopPropagation();}} onPointerMove={e => {const d=drag.current; if (!d || d.id !== n.id) return; onChange({...graph, nodes: graph.nodes.map(item => item.id === n.id ? {...item, position: {x: Math.max(20, Math.round((d.x+(e.clientX-d.startX)/zoom)/16)*16), y: Math.max(20, Math.round((d.y+(e.clientY-d.startY)/zoom)/16)*16)}} : item)});}} onPointerUp={() => {drag.current=null;}} onKeyDown={e => {if (e.key.startsWith("Arrow")) { e.preventDefault(); const dx=e.key === "ArrowRight" ? 16 : e.key === "ArrowLeft" ? -16 : 0; const dy=e.key === "ArrowDown" ? 16 : e.key === "ArrowUp" ? -16 : 0; onChange({...graph,nodes:graph.nodes.map(item => item.id === n.id ? {...item,position:{x:Math.max(20,pos.x+dx),y:Math.max(20,pos.y+dy)}}:item)});}}}>
                <span className="t-micro">{n.role === "trigger" ? "WHEN" : n.role === "condition" ? "IF" : "DO"}</span><strong>{label(n)}</strong><span className="node-summary" title={Object.entries(n.config).map(([k,v]) => `${k}: ${String(v)}`).join(" · ")}>{Object.entries(n.config).filter(([k,v]) => v !== "" && v !== undefined && !["webhook_url", "email_recipients"].includes(k)).slice(0, 2).map(([k,v]) => `${k.replace(/_/g, " ")}: ${String(v)}`).join(" · ") || (n.role === "condition" ? "Routes true or false" : n.role === "trigger" ? "Starts this workflow" : "Runs when reached")}</span><span className="t-caption">{result ? result.ok ? "✓ Passed" : n.role === "action" ? "Failed" : "False / not matched" : "Select to configure"}</span>
              </button>
              <button type="button" className="node-port output" title={n.role === "condition" ? "True output" : "Output"} aria-label={`Output of ${label(n)}`} onClick={() => {setSource({id:n.id,branch:"true"}); setSelected(n.id);}} />
              {n.role === "condition" && <><span className="port-label true">true</span><span className="port-label false">false</span><button type="button" className="node-port output false" title="False output" aria-label={`False output of ${label(n)}`} onClick={() => {setSource({id:n.id,branch:"false"}); setSelected(n.id);}} /></>}
            </div>;
          })}
        </div></div>
      </div>
      {edge && <aside className="node-inspector"><div className="canvas-toolbar"><span className="t-label">Connection</span><button type="button" className="button-secondary-outline" onClick={() => setSelectedEdge(null)}><Ico t="Close" /></button></div><h3>{label(graph.nodes.find(n => n.id === edge.from)!)}</h3><p className="t-caption">{edge.branch || "Next"} output to {label(graph.nodes.find(n => n.id === edge.to)!)}</p><label className="t-caption">Insert a step<select className="text-input" aria-label="Insert a step" value="" onChange={e => insertNode(e.target.value)}><option value="">Choose a condition or action…</option>{labels.filter(l => l.role ? l.role !== "trigger" : !["any_change", "schedule", "threshold", "specific_user", "quality_failure", "new_feature", "schema_change", "layer_presence", "freshness"].includes(l.id)).map(l => <option key={l.id} value={l.id}>{l.label}</option>)}</select></label><button type="button" className="button-secondary-outline" onClick={() => {onChange({...graph, edges: graph.edges.filter((_,i) => i !== selectedEdge)}); setSelectedEdge(null);}}><Ico t="Delete connection" /></button></aside>}
      {node && <aside className="node-inspector"><div className="canvas-toolbar"><span className="t-label">Node settings</span><button type="button" className="button-secondary-outline" onClick={() => setSelected(null)}><Ico t="Close" /></button></div><h3>{label(node)}</h3><p className="t-caption">{labels.find(l => l.id === node.kind)?.description}</p><p className="node-role">{node.role === "trigger" ? "Trigger · no input · one output" : node.role === "condition" ? "Condition · one input · true / false outputs" : "Action · one input · next output"}</p>{renderConfig(node)}<h4>Connections</h4><p className="t-caption">Each reached node runs once. Failed actions stop their downstream path.</p>
        <label className="t-caption">Output<select className="text-input" aria-label="Connection output" value={source?.id === node.id ? source.branch : "true"} onChange={e => setSource({id:node.id, branch:e.target.value as "true"|"false"})}><option value="true">{node.role === "condition" ? "True" : "Next"}</option>{node.role === "condition" && <option value="false">False</option>}</select></label>
        <label className="t-caption">Destination<select className="text-input" aria-label="Connection destination" value={target} onChange={e => {setTarget(e.target.value); if (source?.id !== node.id) setSource({id:node.id,branch:"true"});}}><option value="">Choose node…</option>{graph.nodes.filter(n => n.id !== node.id && n.role !== "trigger").map(n => <option key={n.id} value={n.id}>{label(n)} ({n.id})</option>)}</select></label><button type="button" className="button-secondary-outline" disabled={!target} onClick={() => connect(target)}><Ico t="Connect" /></button>
        {graph.edges.filter(e => e.from === node.id).map(e => <div className="edge-row" key={`${e.to}:${e.branch}`}><span>{e.branch || "Next"} → {label(graph.nodes.find(n => n.id === e.to)!)}</span><button type="button" className="button-secondary-outline" aria-label={`Remove connection to ${e.to}`} onClick={() => onChange({...graph, edges:graph.edges.filter(item => item !== e)})}><Ico t="Remove" /></button></div>)}
        <button type="button" className="button-secondary-outline" onClick={removeNode}><Ico t="Delete node" /></button>
      </aside>}
    </div>
    {trace.length > 0 && <div className="execution-trace"><h3>Execution preview</h3><p className="t-caption">No notifications are sent during a test run.</p>{trace.map((step,i) => <div className="trace-row" key={i}><span>{i+1}</span><strong>{labels.find(l => l.id === step.kind)?.label || step.kind}</strong><span>{step.ok ? "Passed" : step.role === "action" ? "Failed" : "False / not matched"}</span><p>{step.message}</p></div>)}</div>}
  </div>;
}
