import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { getConnections, SavedConnection } from "../api";
import { Link } from "react-router-dom";

export default function ConnectionSettings() {
  const [connections, setConnections] = useState<SavedConnection[]>([]);
  const [editing, setEditing] = useState<SavedConnection | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {getConnections().then(setConnections).catch(e => setError(e.message));}, []);
  async function save() {
    if (!editing) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/connections/${editing.id}`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...editing, password: password || undefined})});
      if (!response.ok) throw Error((await response.json()).detail);
      setEditing(null); setPassword(""); setConnections(await getConnections()); setStatus("Connection tested and saved.");
    } catch(e) {setError(e instanceof Error ? e.message : "Could not save connection.");} finally {setBusy(false);}
  }
  return <section className="connection-settings" id="connections" style={{marginTop: 48}}><h2 className="t-heading-lg">Connections</h2><p className="t-caption">Edit saved connection details or credentials. Changes are tested before saving.</p>
    {connections.map(c => <div className="connection-row" key={c.id} style={{display: "flex", gap: 16, alignItems: "center", marginBottom: 12}}><Link to={`/connections/${c.id}/overview`}>{c.name}</Link><span className="t-caption">{c.type}</span><button type="button" className="button-secondary-outline" onClick={() => {setEditing({...c, config: {...c.config}}); setPassword(""); setStatus("");}}><Ico t="Edit" /></button><button type="button" className="button-secondary-outline" onClick={async () => {if (!window.confirm(`Remove ${c.name} and its cached monitoring results? Source data will remain untouched.`)) return; try {const r = await fetch(`/api/connections/${c.id}`, {method: "DELETE"}); if (!r.ok) throw Error("Could not remove connection."); setConnections(await getConnections());} catch(e) {setError(String(e));}}}><Ico t="Remove" /></button></div>)}
    {editing && <div className="card connection-editor"><h3>Edit connection</h3><label>Name<input className="text-input" value={editing.name} onChange={e => setEditing({...editing, name: e.target.value})} /></label>{Object.entries(editing.config).filter(([,v]) => typeof v === "string" || typeof v === "number").map(([key,value]) => <label key={key} style={{display: "block", marginTop: 12}}>{key}<input className="text-input" value={String(value)} onChange={e => setEditing({...editing, config: {...editing.config, [key]: typeof value === "number" ? Number(e.target.value) : e.target.value}})} /></label>)}{editing.type !== "files" && <label style={{display: "block", marginTop: 12}}>Password (leave blank to keep)<input className="text-input" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /></label>}<button type="button" className="button-primary-dark" disabled={busy} onClick={save}><Ico t={busy ? "Testing…" : "Test & save"} /></button> <button type="button" className="button-secondary-outline" onClick={() => setEditing(null)}><Ico t="Cancel" /></button></div>}
    {error && <p role="alert">{error}</p>}{status && <p role="status">{status}</p>}
  </section>;
}
