import { Ico } from "../components/Icon";
import WorkflowCanvas from "../components/WorkflowCanvas";
import { useEffect, useState, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useAi } from "../shell/AiContext";
import {
  AutoCatalog,
  AutoGraph,
  AutoNode,
  AutoRun,
  Automation,
  createAutomation,
  deleteAutomation,
  getAutomationCatalog,
  getAutomations,
  previewAutomation,
  updateAutomation,
} from "../api";
import { ErrorState, LoadingState } from "../components/States";

const EMPTY: AutoGraph = { nodes: [], edges: [] };

/** FSD §11.2 / DVS §14  -  three-column when→if→do canvas. */
function Automations() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [search, setSearch] = useSearchParams();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [notice, setNotice] = useState("");
  const saveLock = useRef(false);
  const { draftTick } = useAi();
  const [catalog, setCatalog] = useState<AutoCatalog | null>(null);
  const [list, setList] = useState<Automation[]>([]);
  const [runs, setRuns] = useState<AutoRun[]>([]);
  const [current, setCurrent] = useState<Automation | null>(null);
  const [title, setTitle] = useState("");
  const [graph, setGraph] = useState<AutoGraph>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<AutoRun["trace"]>([]);
  const [aiAuthored, setAiAuthored] = useState(false);
  const review = useRef<HTMLDialogElement>(null);
  const [glow, setGlow] = useState<string | null>(null);

  function load() {
    if (!connectionId) return;
    getAutomationCatalog(connectionId).then(setCatalog).catch((err) => setError(err.message));
    getAutomations(connectionId)
      .then((body) => {setList(body.automations); setRuns(body.runs || []);})
      .catch((err) => setError(err.message));
  }

  useEffect(load, [connectionId]);
  useEffect(() => {
    if (!search.get("edit")) {setCurrent(null); setGraph(EMPTY); setTitle(""); setTrace([]); setGlow(null); setError(null);}
  }, [search]);
  useEffect(() => {
    const id = search.get("edit");
    if (!id || id === "draft" || current) return;
    const saved = list.find(item => item.id === id);
    if (saved) {setCurrent(saved); setTitle(saved.title); setGraph(saved.graph);}
  }, [list, search, current]);

  useEffect(() => {
    if (!connectionId) return;
    const raw = sessionStorage.getItem(`tarsier-auto-draft-${connectionId}`);
    if (!raw) return;
    try {
      const draft = JSON.parse(raw);
      if (draft.graph) {
        setSearch({edit: "draft"});
        setAiAuthored(true);
        setTitle(draft.title || "AI draft");
        setGraph(draft.graph);
        setCurrent(null);
        setTrace([]);
        setGlow(null);
      }
    } catch {
      /* ignore */
    }
  }, [connectionId, draftTick]);

  async function save(approved = false) {
    if (aiAuthored && !approved) { review.current?.showModal(); return; }
    if (!connectionId || saveLock.current) return;
    saveLock.current = true; setSaving(true); setError(null);
    try {
      if (current) {
        const updated = await updateAutomation(connectionId, current.id, { title, graph, paused: current.paused, ai_authored: aiAuthored, review_approved: approved });
        setCurrent(updated);
      } else {
        const created = await createAutomation(connectionId, { title, graph, ai_authored: aiAuthored, review_approved: approved });
        setCurrent(created);
        setSearch({edit: created.id}, {replace: true});
      }
      setNotice("Automation saved. Future saves update this same automation.");
      review.current?.close();
      setAiAuthored(false);
      sessionStorage.removeItem(`tarsier-auto-draft-${connectionId}`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {saveLock.current = false; setSaving(false);}
  }

  async function fromTemplate(id: string) {
    if (!connectionId) return;
    try {
      const response = await fetch(`/api/connections/${connectionId}/automations/templates/${id}`);
      if (!response.ok) throw Error("Could not load template.");
      const template = await response.json();
      setSearch({edit: "draft"}); setNotice("");
      setCurrent(null); setTitle(template.title); setGraph(template.graph); setAiAuthored(false); setTrace([]); setGlow(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not load template."); }
  }

  async function runTest() {
    if (!connectionId) return;
    if (testing) return;
    setTesting(true); setError(null); setTrace([]); setGlow(null);
    try {
      const result = await previewAutomation(connectionId, {title, graph});
      setNotice(result.message);
      setTrace(result.trace);
      for (const step of result.trace) {
        setGlow(step.node_id);
        await new Promise((r) => setTimeout(r, 250));
      }
      setGlow(result.trace[result.trace.length - 1]?.node_id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test run failed.");
    } finally {setTesting(false);}
  }

  if (!connectionId) return null;
  if (error && !catalog) {
    return <ErrorState message={error} onRetry={() => { setError(null); load(); }} />;
  }
  if (!catalog) {
    return <LoadingState label="Loading automations" />;
  }

  const showingCanvas = !!search.get("edit") || current != null || graph.nodes.length > 0 || title.length > 0;

  return (
    <div>
      <h1 className="t-display-lg">Automations</h1>
      <dialog ref={review} className="review-dialog" aria-labelledby="review-title">
        <h2 id="review-title" className="t-display-md">Review before saving</h2>
        <p>Tarsier never saves or runs anything from AI without your approval.</p>
        <p>{title}</p>
        <div className="review-nodes">{graph.nodes.map(node => <div className="review-node" key={node.id}><strong>{node.role}: {node.kind}</strong><pre>{JSON.stringify(node.config, null, 2)}</pre></div>)}</div>
        <p className="t-caption">{graph.edges.map(e => `${e.from} to ${e.to}`).join(" / ")}</p>
        <button className="button-primary-dark" onClick={() => save(true)}><Ico t="Approve & save" /></button>{" "}
        <button className="button-secondary-outline" onClick={() => review.current?.close()}><Ico t="Edit first" /></button>{" "}
        <button className="button-secondary-outline" onClick={() => {review.current?.close(); setSearch({}, {replace: true}); setGraph(EMPTY); setTitle(""); setAiAuthored(false); sessionStorage.removeItem(`tarsier-auto-draft-${connectionId}`);}}><Ico t="Discard" /></button>
      </dialog>
      {error && (
        <p role="alert" style={{ color: "var(--status-danger)" }}>
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!showingCanvas && (
        <div>
          <p className="t-body-md">Build workflows for data changes, quality, statistics, and reporting.</p>
          <section className="card"><h2 className="t-heading-lg">Your saved automations ({list.length})</h2><p className="t-caption">These are your workflows. Templates below are starting points and are not saved automations.</p>
          {!list.length ? <p>No saved automations yet. Start with a blank canvas or a template.</p> : <div className="saved-automations">{list.map(item => <article className="saved-automation" key={item.id}><div><strong>{item.title}</strong><p className="t-caption">{item.paused ? "Paused" : "Active"} · {item.graph.nodes.length} steps · {item.last_run_at ? `Last run ${new Date(item.last_run_at).toLocaleString()}` : "Has not run yet"} · ID {item.id.slice(0, 8)}</p></div><div className="row-actions"><button className="button-secondary-outline" onClick={() => {setSearch({edit: item.id}); setCurrent(item); setTitle(item.title); setGraph(item.graph); setTrace([]); setNotice(""); setAiAuthored(false);}}><Ico t="Edit" /></button><button className="button-secondary-outline" onClick={async () => {try {await updateAutomation(connectionId, item.id, {...item, paused: !item.paused}); load();} catch(e) {setError(e instanceof Error ? e.message : "Could not update.");}}}><Ico t={item.paused ? "Resume" : "Pause"} /></button><button className="button-secondary-outline" onClick={async () => {try {await deleteAutomation(connectionId, item.id); load();} catch(e) {setError(e instanceof Error ? e.message : "Could not delete.");}}}><Ico t="Delete" /></button></div></article>)}</div>}</section>
          <h2 className="t-heading-lg">Create an automation</h2>
          <div className="automation-templates">
            <button type="button" className="card blank-canvas" onClick={() => {setSearch({edit: "draft"}); setCurrent(null); setTitle("New automation"); setGraph(EMPTY); setNotice(""); setAiAuthored(false);}}><span className="template-tag">Start from scratch</span><strong>+ Blank canvas</strong><p className="t-caption">Choose a trigger, connect conditions, and add actions.</p></button>
            {catalog.templates.map(t => <button key={t.id} type="button" className="card template-card" onClick={() => fromTemplate(t.id)}><span className="template-tag">Template</span><strong>{t.title}</strong><p className="t-caption">{t.blurb}</p></button>)}
          </div>
          {runs.length > 0 && <section className="card" style={{marginTop: 24}}><h2 className="t-heading-lg">Recent executions</h2><p className="t-caption">Saved active automations run while Tarsier is open. Test runs skip actions and deliveries.</p>{runs.map((run, i) => <details className="automation-run" key={run.id || i}><summary>{list.find(item => item.id === run.automation_id)?.title || "Automation"} · {run.dry_run ? "Test" : "Live"} · {run.ok ? "Completed" : "Not completed"} · {run.ran_at ? new Date(run.ran_at).toLocaleString() : ""}</summary><p>{run.message}</p><ol>{run.trace.map((step, j) => <li key={j}>{step.kind}: {step.message || (step.ok ? "Matched" : "Not matched")}</li>)}</ol></details>)}</section>}
        </div>
      )}

      {showingCanvas && catalog && (
        <Canvas
          busy={saving || testing}
          catalog={catalog}
          title={title}
          graph={graph}
          glow={glow}
          trace={trace}
          onTitle={setTitle}
          onGraph={next => {setGraph(next); setTrace([]); setGlow(null);}}
          onSave={() => save()}
          onTest={runTest}
          onBack={() => {
            setSearch({}, {replace: true}); setNotice("");
            setCurrent(null);
            setAiAuthored(false);
            sessionStorage.removeItem(`tarsier-auto-draft-${connectionId}`);
            setTitle("");
            setGraph(EMPTY);
            setTrace([]);
            setGlow(null);
          }}
          onDelete={
            current && connectionId
              ? async () => {
                  await deleteAutomation(connectionId, current.id);
                  setSearch({}, {replace: true});
                  setCurrent(null);
                  setTitle("");
                  setGraph(EMPTY);
                  load();
                }
              : undefined
          }
        />
      )}
    </div>
  );
}

function Canvas({
  busy,
  catalog,
  title,
  graph,
  glow,
  trace,
  onTitle,
  onGraph,
  onSave,
  onTest,
  onBack,
  onDelete,
}: {
  busy: boolean;
  catalog: AutoCatalog;
  title: string;
  graph: AutoGraph;
  glow: string | null;
  trace: AutoRun["trace"];
  onTitle: (v: string) => void;
  onGraph: (g: AutoGraph) => void;
  onSave: () => void;
  onTest: () => void;
  onBack: () => void;
  onDelete?: () => void;
}) {
  const last = graph.nodes[graph.nodes.length - 1];

  function add(role: AutoNode["role"], kind: string) {
    const id = `${role[0]}-${crypto.randomUUID()}`;
    const node: AutoNode = { id, role, kind, config: kind === "schedule" ? {hour: 18, minute: 0} : kind === "run_quality" ? {continue_on_pass: true} : {} };
    const edges = [...graph.edges];
    if (last && role !== "trigger") edges.push({ from: last.id, to: id });
    onGraph({ nodes: [...graph.nodes, node], edges });
  }

  function patch(id: string, config: Record<string, unknown>) {
    onGraph({
      ...graph,
      nodes: graph.nodes.map((n) => (n.id === id ? { ...n, config: { ...n.config, ...config } } : n)),
    });
  }

  return (
    <div>
      <div className="automation-toolbar">
        <button type="button" className="button-secondary-outline" onClick={onBack}><Ico t="Back to automations" /></button>
        <input className="text-input" value={title} onChange={(e) => onTitle(e.target.value)} aria-label="Automation title" />
        <button type="button" className="button-primary-dark" disabled={busy} onClick={onSave}><Ico t="Save" /></button>
        <button type="button" className="button-secondary-outline" disabled={busy} onClick={onTest}><Ico t="Test run" /></button>
        {onDelete && (
          <button type="button" className="button-secondary-outline" onClick={onDelete}><Ico t="Delete" /></button>
        )}
      </div>
      <div className="automation-palette">
        <Palette label="Triggers" items={catalog.triggers} onAdd={(kind) => add("trigger", kind)} />
        <Palette label="Conditions" items={catalog.conditions} onAdd={(kind) => add("condition", kind)} />
        <Palette label="Actions" items={catalog.actions} onAdd={(kind) => add("action", kind)} />
      </div>
      <WorkflowCanvas graph={graph} onChange={onGraph} glow={glow} trace={trace}
        labels={[...catalog.triggers.map(n => ({...n, role: "trigger" as const})), ...catalog.conditions.map(n => ({...n, role: "condition" as const})), ...catalog.actions.map(n => ({...n, role: "action" as const}))]}
        renderConfig={node => <NodeFields node={node} onPatch={patch} />} />
    </div>
  );
}

function Palette({
  label,
  items,
  onAdd,
}: {
  label: string;
  items: { id: string; label: string }[];
  onAdd: (kind: string) => void;
}) {
  return (
    <label className="t-caption">
      Add {label.toLowerCase().slice(0, -1)}
      <select
        className="text-input"
        defaultValue=""
        aria-label={`Add ${label.toLowerCase().slice(0, -1)}`}
        onChange={(e) => {
          if (e.target.value) onAdd(e.target.value);
          e.target.value = "";
        }}
        style={{ display: "block" }}
      >
        <option value="">Add {label.toLowerCase()}…</option>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function NodeFields({node, onPatch}: {node: AutoNode; onPatch: (id: string, config: Record<string, unknown>) => void}) {
  const cfg = node.config;
  const patch = (key: string, value: unknown) => onPatch(node.id, {[key]: value});
  const input = (key: string, label: string, fallback = "", type = "text", min?: number, max?: number) => <label key={key}>{label}<input className="text-input" type={type} min={min} max={max} placeholder={key === "webhook_url" && cfg.webhook_ref ? "Saved - leave blank to keep it" : undefined} value={String(cfg[key] ?? fallback)} onChange={e => patch(key, type === "number" ? (e.target.value === "" ? undefined : Number(e.target.value)) : e.target.value)} /></label>;
  const select = (key: string, label: string, options: [string, string][], fallback: string) => <label key={key}>{label}<select className="text-input" value={String(cfg[key] ?? fallback)} onChange={e => patch(key, e.target.value)}>{options.map(([id, text]) => <option key={id} value={id}>{text}</option>)}</select></label>;
  const message = <label>Message<textarea className="text-input" rows={3} value={String(cfg.message ?? "")} onChange={e => patch("message", e.target.value)} /></label>;
  const target = <>{input("schema", "Schema (optional)")}{input("layer", "Layer (blank for all)")}</>;
  const notify = String(cfg.notify ?? "log");
  return <div className="node-settings">
    {["layer_eq", "run_quality", "scan_statistics", "value_out_of_range", "quality_below", "has_failures", "item_kind", "event_action", "freshness", "layer_presence", "schema_change", "count_drop"].includes(node.kind) && target}
    {["specific_user", "user_eq"].includes(node.kind) && input("user", "Database user")}
    {node.kind === "schedule" && <>{input("hour", "Daily hour (UTC)", "18", "number", 0, 23)}{input("minute", "Minute", "0", "number", 0, 59)}{input("every_minutes", "Or repeat every N minutes", "", "number", 1)}<p className="t-caption">An interval overrides the daily time. Tarsier must be running.</p></>}
    {node.kind === "any_change" && <label className="checkbox-field"><input type="checkbox" checked={Boolean(cfg.mass_only)} onChange={e => patch("mass_only", e.target.checked)} /> Mass changes only</label>}
    {node.kind === "run_quality" && <label className="checkbox-field"><input type="checkbox" checked={Boolean(cfg.continue_on_pass)} onChange={e => patch("continue_on_pass", e.target.checked)} /> Continue when checks pass</label>}
    {node.kind === "threshold" && <p className="t-caption">Row count down 25%, size up 50%, or quality score down 10 points. The first evaluation sets a baseline.</p>}
    {node.kind === "count_drop" && input("percent", "Minimum drop (%)", "25", "number", .01, 100)}
    {node.kind === "freshness" && input("threshold_days", "Days since last update", "90", "number", 1, 36500)}
    {node.kind === "quality_below" && input("score", "Score below (0 to 100)", "80", "number", 0, 100)}
    {node.kind === "layer_presence" && select("presence", "Inventory change", [["either", "Added or removed"], ["added", "Added"], ["dropped", "Removed"]], "either")}
    {node.kind === "event_action" && select("action", "Change action", [["insert", "Insert"], ["update", "Update"], ["delete", "Delete"], ["schema", "Schema change"]], "delete")}
    {node.kind === "item_kind" && select("item_kind", "Item type", [["vector", "Vector layer"], ["tabular", "Table"], ["raster", "Raster"]], "vector")}
    {node.kind === "change_report" && select("interval", "Report period", [["daily", "Last day"], ["weekly", "Last week"]], "daily")}
    {node.kind === "value_out_of_range" && <>{input("field", "Field")}{select("operator", "Comparison", [["eq", "Equals"], ["ne", "Does not equal"], ["gt", "Greater than"], ["gte", "At least"], ["lt", "Less than"], ["lte", "At most"], ["is_null", "Is empty"], ["is_not_null", "Is not empty"]], "eq")}{!["is_null", "is_not_null"].includes(String(cfg.operator)) && input("value", "Value")}</>}
    {node.kind === "log" && message}
    {node.kind === "chat" && <>{select("channel", "Saved channel", [["slack", "Slack"], ["teams", "Teams"]], "slack")}{message}</>}
    {node.kind === "webhook" && input("webhook_url", "Webhook URL", "", "url")}
    {node.kind === "email" && <>{input("email_recipients", "Recipient emails (comma-separated)")}{input("subject", "Subject")}{message}</>}
    {node.kind === "ai_summarize" && <>{select("notify", "Deliver summary to", [["log", "Run history only"], ["email", "Email"], ["webhook", "Webhook"], ["slack", "Slack"], ["teams", "Teams"]], "log")}{notify === "email" && input("email_recipients", "Recipient emails (comma-separated)")}{notify === "webhook" && input("webhook_url", "Webhook URL", "", "url")}</>}
  </div>;
}

export default Automations;
