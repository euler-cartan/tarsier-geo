import { Ico } from "./Icon";
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AiQueryResult, getAiSettings, runAiQuery, StatsRow } from "../api";
import MapPreview from "./MapPreview";

type Turn = {id: string; question: string; answer: string; state: "pending" | "done" | "error"; model: string};
const readHistory = (key: string): Turn[] => {
  try {return JSON.parse(sessionStorage.getItem(key) || "[]").map((turn: Turn) => turn.state === "pending" ? {...turn,state:"error",answer:"The question was interrupted. Send it again to retry."} : turn);} catch {return [];}
};

function AiQueryBox({connectionId,schema,name}: {connectionId:string;schema:string;name:string}) {
  const historyKey = `tarsier-query-${connectionId}-${schema}-${name}`;
  const [configured,setConfigured] = useState<boolean|null>(null);
  const [privacyWarning,setPrivacyWarning] = useState<string|null>(null);
  const [model,setModel] = useState("");
  const [question,setQuestion] = useState("");
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState<AiQueryResult|null>(null);
  const [turns,setTurns] = useState<Turn[]>(() => readHistory(historyKey));
  useEffect(() => {setTurns(readHistory(historyKey)); setResult(null); setQuestion("");}, [historyKey]);
  useEffect(() => {
    getAiSettings().then(settings => {setConfigured(settings.configured);setPrivacyWarning(settings.privacy_warning);setModel(`${settings.provider === "external" ? "OpenRouter" : "Ollama"} · ${settings.model || "Configured model"}`);}).catch(() => setConfigured(false));
  }, []);
  function update(next: Turn[]) {
    setTurns(next);
    try {sessionStorage.setItem(historyKey,JSON.stringify(next.slice(-20)));} catch { /* The visible conversation still works when session storage is full. */ }
  }
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    const sent = question.trim(), id = crypto.randomUUID();
    const pending: Turn = {id,question:sent,answer:"Waiting for the model…",state:"pending",model};
    const next = [...turns,pending]; update(next); setQuestion(""); setBusy(true); setResult(null);
    try {
      const answer = await runAiQuery(connectionId,schema,name,sent);
      setResult(answer);
      update(next.map(turn => turn.id === id ? {...turn,state:"done",answer:`${answer.rows.length} matching rows. Filter: ${answer.caption}${answer.is_sample ? " (sample-based)" : ""}`} : turn));
    } catch (error) {
      update(next.map(turn => turn.id === id ? {...turn,state:"error",answer:error instanceof Error ? error.message : "Could not run that question."} : turn));
    } finally {setBusy(false);}
  }
  if (configured === null) return <div className="skeleton" style={{height:72}} />;
  if (!configured) return <div className="query-assistant" role="status">Set up AI first in <Link to="/settings">Settings</Link> to ask questions in plain English. Everything else in Tarsier still works.</div>;
  return <section className="query-assistant" aria-label="Layer AI questions">
    <div className="query-header"><div><h2 className="t-heading-lg" style={{margin:0}}>Ask about this layer</h2><p className="t-caption">{model}</p></div>{turns.length > 0 && <button type="button" className="button-secondary-outline" disabled={busy} onClick={() => {update([]);setResult(null);}}><Ico t="Clear history" /></button>}</div>
    <p className="t-caption">Each question runs independently against {name}. The AI receives your question and column descriptions, not raw rows. History stays in this browser session.</p>
    {privacyWarning && <p className="t-caption" role="status">{privacyWarning}</p>}
    <div className="query-conversation" aria-live="polite">{turns.map(turn => <article className="query-turn" key={turn.id}><span className="t-label">You asked</span><blockquote>{turn.question}</blockquote><span className="t-label">{turn.model}</span><p role={turn.state === "error" ? "alert" : turn.state === "pending" ? "status" : undefined}>{turn.answer}</p></article>)}</div>
    <form className="query-composer" onSubmit={onSubmit}><input className="text-input" placeholder="Ask about this data…" aria-label="Ask about this data" value={question} onChange={e=>setQuestion(e.target.value)} disabled={busy} /><button type="submit" className="button-primary-dark" disabled={busy || !question.trim()}><Ico t={busy ? "Thinking…" : "Ask"} /></button></form>
    {result && <div style={{marginTop:20}}><p className="t-caption">Showing: {result.caption}</p><RowsTable rows={result.rows} /><FlagMap rows={result.rows} /></div>}
  </section>;
}

export function RowsTable({ rows }: { rows: StatsRow[] }) {
  if (rows.length === 0) {
    return <p className="t-caption">No matching rows.</p>;
  }
  const keys = Object.keys(rows[0]).filter((k) => k !== "centroid_x" && k !== "centroid_y" && k !== "geometry_missing");
  return (
    <div className="table-scroll"><table className="data-table result-table" style={{minWidth: Math.max(900, keys.length * 160)}}>
      <thead>
        <tr>
          {keys.map((k) => (
            <th key={k}>{k}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {keys.map((k) => (
              <td key={k}>{row[k] == null ? " - " : String(row[k])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

export function FlagMap({ rows }: { rows: StatsRow[] }) {
  const points = rows
    .map((row) => ({ x: Number(row.centroid_x), y: Number(row.centroid_y) }))
    .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (points.length === 0) return null;
  return (
    <div style={{ marginTop: "var(--space-4)" }}>
      <MapPreview bbox={null} points={points} height={220} />
    </div>
  );
}

export default AiQueryBox;
