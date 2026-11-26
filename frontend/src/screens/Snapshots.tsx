import { Ico } from "../components/Icon";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { LoadingState } from "../components/States";

type Version = {id: string; schema: string; name: string; created_at: string; row_count: number; geospatial: boolean; schema_changed: boolean; projection_changed: boolean};
type Plan = {filter: unknown; caption: string};
type Result = {count: number; rows: Record<string, unknown>[]; sql: string; params: unknown[]; filter: {caption: string} | null};
async function request(url: string, body?: unknown) {
  const response = await fetch(url, body === undefined ? undefined : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Error(data.detail || "Request failed.");
  return data;
}

export default function Snapshots() {
  const {connectionId} = useParams();
  const base = `/api/connections/${connectionId}/snapshots`;
  const [versions, setVersions] = useState<Version[]>([]);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [selected, setSelected] = useState("");
  const [before, setBefore] = useState("");
  const [question, setQuestion] = useState("");
  const [sentQuestion, setSentQuestion] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [bounds, setBounds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [comparison, setComparison] = useState<{added: number | null; removed: number | null; message: string} | null>(null);
  const explorer = useRef<HTMLElement>(null);
  const exploreButton = useRef<string>("");
  async function load() {const data = await request(base); setVersions(data.versions); setAvailable(data.available);}
  useEffect(() => {setSelected(""); setAvailable(null); load().catch(e => setError(e.message));}, [connectionId]);
  useEffect(() => {if (selected) {explorer.current?.focus(); window.scrollTo?.({top: 0, behavior: "smooth"});} else if (exploreButton.current) document.getElementById(exploreButton.current)?.focus();}, [selected]);
  async function run(action: () => Promise<void>) {setBusy(true); setError(""); try {await action();} catch(e) {setError(e instanceof Error ? e.message : "Could not complete this operation.");} finally {setBusy(false);}}
  const active = versions.find(v => v.id === selected);
  function resetSearch() {setPlan(null); setResult(null);}
  return <div>
    <div className="page-heading"><div><p className="t-label">Local data history</p><h1 className="t-display-lg">Snapshots & analytics</h1></div>{available && !active && <button className="button-primary-dark" disabled={busy} onClick={() => run(async () => {const data = await request(base + "/capture", {}); setNotice(`Captured ${data.versions.length} item versions. ${data.unavailable.map((x: {name: string; message: string}) => `${x.name}: ${x.message}`).join(" ")}`); await load();})}><Ico t={busy ? "Capturing…" : "Capture snapshot"} /></button>}</div>
    <p className="t-caption">Database snapshots every 2 days · 90-day retention · Queries run on local copies</p>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {available === null && !error && <LoadingState label="Loading snapshots" />}
    {available === false && <div className="card"><h2 className="t-display-sm">Snapshots are available for databases</h2><p>File connections are not versioned. Statistics and quality checks remain available.</p><Link to={`/connections/${connectionId}/overview`}>Back to overview</Link></div>}
    {available && !active && (!versions.length ? <div className="card"><h2 className="t-display-sm">Your first point in time</h2><p>Capture a database snapshot to search and compare data without querying the live source.</p></div> : <div className="card table-scroll"><table className="data-table"><thead><tr><th>Item</th><th>Captured</th><th>Rows</th><th>Format / drift</th><th>Explore</th></tr></thead><tbody>{versions.map(v => <tr key={v.id}><td>{v.schema ? v.schema + "." : ""}{v.name}</td><td>{new Date(v.created_at).toLocaleString()}</td><td className="numeric">{v.row_count.toLocaleString()}</td><td>{v.geospatial ? "GeoParquet" : "Parquet"}{v.schema_changed && " · Schema changed"}{v.projection_changed && " · CRS changed"}</td><td><button id={`explore-${v.id}`} className="button-secondary-outline" onClick={() => {exploreButton.current = `explore-${v.id}`; setSelected(v.id); resetSearch(); setQuestion(""); setBounds(""); setComparison(null); setBefore(""); setError("");}}><Ico t="Explore" /></button></td></tr>)}</tbody></table></div>)}
    {active && <section ref={explorer} tabIndex={-1} className="card snapshot-explorer" aria-label="Snapshot explorer">
      <button className="button-secondary-outline" disabled={busy} onClick={() => {setSelected(""); setError("");}}><Ico t="Back to snapshots" /></button>
      <h2 className="t-display-md">Explore {active.schema ? `${active.schema}.` : ""}{active.name}</h2><p className="t-caption">Snapshot {active.id.slice(0, 8)} · {new Date(active.created_at).toLocaleString()} · {active.row_count.toLocaleString()} rows</p>
      <label>Ask about this snapshot<textarea className="text-input" value={question} onChange={e => {setQuestion(e.target.value); resetSearch();}} rows={3} placeholder="Items with fewer than 10 units in stock" /></label>
      <p className="t-caption">AI receives column descriptions, not rows. <Link to="/settings">AI settings</Link>. Use Ollama for private AI. Comparisons and empty values can be joined with AND or OR. Ambiguous or unsupported requests require clarification.</p>
      {active.geospatial && <label>Optional map bounds (WGS84)<input className="text-input" value={bounds} onChange={e => {setBounds(e.target.value); resetSearch();}} placeholder="west, south, east, north" /></label>}
      <button className="button-primary-dark" disabled={busy} onClick={() => run(async () => {resetSearch(); setSentQuestion(question.trim() || "Show all rows"); setPlan(await request(`${base}/${selected}/plan`, {question}));})}><Ico t={busy ? "Working…" : "Review search"} /></button>
      {plan && <div className="search-plan" role="status"><p className="t-label">Your instruction</p><p>{sentQuestion}</p><p className="t-label">Filter to execute</p><p>{plan.caption}</p>{bounds.trim() && <p>Map bounds: {bounds}</p>}<button className="button-primary-dark" disabled={busy} onClick={() => run(async () => {const bbox = bounds.trim() && active.geospatial ? bounds.split(",").map(Number) : null; if (bbox && (bbox.length !== 4 || bbox.some(n => !Number.isFinite(n)))) throw Error("Enter four numeric bounds."); setResult(await request(`${base}/${selected}/query`, {filter_payload: plan.filter, bbox}));})}><Ico t="Run search" /></button></div>}
      {result && <div style={{marginTop: 24}}><p>{result.count.toLocaleString()} matching rows · displaying up to 200</p><p>{result.filter?.caption || "All rows"}</p><details><summary>Show what ran on the local snapshot</summary><pre style={{whiteSpace: "pre-wrap"}}>{result.sql}{"\n"}Parameters: {JSON.stringify(result.params)}</pre></details>{result.rows.length > 0 ? <div className="table-scroll snapshot-results" tabIndex={0} aria-label="Snapshot search results"><table className="data-table" style={{minWidth: Math.max(700, Object.keys(result.rows[0]).length * 180)}}><colgroup>{Object.keys(result.rows[0]).map(k => <col key={k} style={{width: 180}} />)}</colgroup><thead><tr>{Object.keys(result.rows[0]).map(k => <th key={k} title={k}>{k}</th>)}</tr></thead><tbody>{result.rows.map((row, i) => <tr key={i}>{Object.entries(row).map(([k,v]) => <td key={k} className={typeof v === "number" ? "numeric" : ""} title={v === null ? "No value" : String(v)}>{v === null ? "No value" : String(v)}</td>)}</tr>)}</tbody></table></div> : <p>No rows match this search.</p>}</div>}
      <h3 className="t-heading-lg">Compare versions</h3><div className="form-actions"><label>Earlier version<select className="text-input" value={before} onChange={e => setBefore(e.target.value)}><option value="">Choose an earlier version</option>{versions.filter(v => v.name === active.name && v.schema === active.schema && v.created_at < active.created_at).map(v => <option key={v.id} value={v.id}>{new Date(v.created_at).toLocaleString()}</option>)}</select></label><button className="button-secondary-outline" disabled={!before || busy} onClick={() => run(async () => setComparison(await request(`${base}/compare?before=${before}&after=${selected}`)))}><Ico t="Compare" /></button></div>
      {comparison && <p role="status">{comparison.added ?? "Unavailable"} added · {comparison.removed ?? "Unavailable"} removed. {comparison.message}</p>}
    </section>}
  </div>;
}
