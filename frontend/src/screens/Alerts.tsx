import { Ico } from "../components/Icon";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  AlertKind,
  AlertRule,
  createAlert,
  deleteAlert,
  evaluateAlerts,
  getAlerts,
  updateAlert,
} from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/States";
import StatusBadge from "../components/StatusBadge";

/** FSD §11.1 Alerts list + create/edit/pause/delete for every PRD §7.5 type. */
function Alerts() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [kinds, setKinds] = useState<AlertKind[]>([]);
  const [fires, setFires] = useState<{ message: string; fired_at: string; channel: string; delivery_status: string; delivery_message: string | null }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<AlertRule | null>(null);

  function load() {
    if (!connectionId) return;
    getAlerts(connectionId)
      .then((body) => {
        setRules(body.rules);
        setKinds(body.kinds);
        setFires(body.fires);
        setLoaded(true);
        setError(null);
      })
      .catch((err) => setError(err.message));
  }

  useEffect(load, [connectionId]);

  if (!connectionId) return null;
  if (error && !loaded) {
    return <ErrorState message={error} onRetry={() => { setError(null); load(); }} />;
  }
  if (!loaded) {
    return <LoadingState label="Loading alerts" />;
  }

  return (
    <div>
      <div className="page-heading">
        <h1 className="t-display-lg">Alerts</h1>
        <button type="button" className="button-secondary-outline" disabled={busy} onClick={async () => {setBusy(true); setNotice(""); try {await evaluateAlerts(connectionId); setNotice("Evaluation complete. Matches and delivery results appear below. The first comparison evaluation establishes a baseline."); load();} catch (e) {setError(e instanceof Error ? e.message : "Evaluation failed.");} finally {setBusy(false);}}}><Ico t={busy ? "Evaluating…" : "Evaluate now"} /></button>
      </div>
      <p className="t-caption">Alerts monitor one condition and record each match. Automations connect triggers, branches, and actions into a workflow. These monitors use cached scans and recorded changes. Older alerts without a sample label have unknown sampling scope and must not be treated as full checks.</p>
      {notice && <p role="status">{notice}</p>}
      {error && (
        <p style={{ color: "var(--status-danger)" }} role="alert">
          {error}
        </p>
      )}
      {rules.length === 0 && (
        <EmptyState title="No alerts yet">
          Alerts tell you when something important changes. Create your first one with the form below.
        </EmptyState>
      )}
      {rules.length > 0 && (
      <section className="card"><h2 className="t-heading-lg">Saved alerts ({rules.length})</h2><div className="table-scroll"><table className="data-table alerts-table">
        <thead>
          <tr>
            <th>Alert</th>
            <th>Type</th>
            <th>Target</th>
            <th>Condition</th>
            <th>Status</th>
            <th>Last triggered</th>
            <th>Manage</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.id}>
              <td>{rule.title}</td>
              <td>{kinds.find((k) => k.id === rule.kind)?.label ?? rule.kind}</td>
              <td>{rule.target_name ? `${rule.target_schema ? rule.target_schema + "." : ""}${rule.target_name}` : rule.target_schema ? `Schema: ${rule.target_schema}` : "Whole connection"}</td>
              <td className="t-caption">{conditionSummary(rule)}</td>
              <td>
                <StatusBadge kind={rule.paused ? "neutral" : "good"} label={rule.paused ? "paused" : "active"} />
              </td>
              <td className="t-caption">{rule.last_triggered_at ? new Date(rule.last_triggered_at).toLocaleString() : "Not triggered"}</td>
              <td><div className="row-actions">
                <button type="button" className="button-secondary-outline" onClick={() => {setEditing(rule); document.getElementById("alert-editor")?.scrollIntoView?.({behavior: "smooth", block: "start"});}}><Ico t="Edit" /></button>{" "}
                <button
                  type="button"
                  className="button-secondary-outline"
                  onClick={() =>
                    updateAlert(connectionId, rule.id, { ...rule, paused: !rule.paused }).then(load).catch(e => setError(e.message))
                  }
                ><Ico t={rule.paused ? "Resume" : "Pause"} /></button>{" "}
                <button type="button" className="button-secondary-outline" onClick={() => deleteAlert(connectionId, rule.id).then(load).catch(e => setError(e.message))}><Ico t="Delete" /></button></div>
              </td>
            </tr>
          ))}
        </tbody>
      </table></div></section>
      )}

      <AlertForm
        connectionId={connectionId}
        kinds={kinds}
        existing={editing}
        onDone={() => {
          setEditing(null);
          load();
        }}
        onError={setError}
      />

      {fires.length > 0 && (
        <div className="card" style={{ marginTop: "var(--space-6)" }}>
          <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
            Alert history
          </h2>
          <ul>
            {fires.slice(0, 20).map((fire, i) => (
              <li key={i} className="t-caption">
                {fire.fired_at}: {fire.message} ({fire.channel}: {fire.delivery_status}{fire.delivery_message ? `  -  ${fire.delivery_message}` : ""})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AlertForm({
  connectionId,
  kinds,
  existing,
  onDone,
  onError,
}: {
  connectionId: string;
  kinds: AlertKind[];
  existing: AlertRule | null;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [kind, setKind] = useState(existing?.kind ?? "mass_change");
  const [title, setTitle] = useState(existing?.title ?? "");
  const [schema, setSchema] = useState(existing?.target_schema ?? "");
  const [threshold, setThreshold] = useState(25);
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState("");
  const [target, setTarget] = useState(existing?.target_name ?? "");
  const [user, setUser] = useState(String(existing?.config.user ?? ""));
  const [field, setField] = useState(String(existing?.config.field ?? ""));
  const [operator, setOperator] = useState(String(existing?.config.operator ?? "eq"));
  const [value, setValue] = useState(String(existing?.config.value ?? ""));
  const [notify, setNotify] = useState(String(existing?.config.notify ?? "log"));
  const [webhook, setWebhook] = useState(String(existing?.config.webhook_url ?? ""));
  const [emailRecipients, setEmailRecipients] = useState(String(existing?.config.email_recipients ?? ""));
  const [presence, setPresence] = useState(String(existing?.config.presence ?? "either"));

  useEffect(() => {
    setKind(existing?.kind ?? "mass_change");
    setTitle(existing?.title ?? "");
    setSchema(existing?.target_schema ?? "");
    setThreshold(existing?.kind === "freshness" ? Number(existing.config.threshold_days ?? 90) : existing?.kind === "quality_score_drop" ? Number(existing.config.threshold_points ?? 10) : Number(existing?.config.threshold_share ?? (existing?.kind === "size_spike" ? .5 : .25)) * 100);
    setPreview("");
    setTarget(existing?.target_name ?? "");
    setUser(String(existing?.config.user ?? ""));
    setField(String(existing?.config.field ?? ""));
    setOperator(String(existing?.config.operator ?? "eq"));
    setValue(String(existing?.config.value ?? ""));
    setNotify(String(existing?.config.notify ?? "log"));
    setWebhook(String(existing?.config.webhook_url ?? ""));
    setEmailRecipients(String(existing?.config.email_recipients ?? ""));
    setPresence(String(existing?.config.presence ?? "either"));
  }, [existing]);

  function body() {return {
      kind,
      title: title || kinds.find((k) => k.id === kind)?.label || kind,
      target_schema: schema,
      target_name: target,
      config: {
        notify,
        webhook_url: webhook,
        email_recipients: emailRecipients,
        user,
        field,
        operator,
        value,
        presence,
        ...(kind === "freshness" ? {threshold_days: threshold} : kind === "quality_score_drop" ? {threshold_points: threshold} : ["row_count_drop", "size_spike"].includes(kind) ? {threshold_share: threshold / 100} : {}),
      },
      paused: existing?.paused ?? false,
    };}
  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    const payload = body();
    try {
      if (existing) await updateAlert(connectionId, existing.id, payload);
      else await createAlert(connectionId, payload);
      onDone();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save that alert.");
    } finally {setSaving(false);}
  }

  return (
    <form id="alert-editor" className="card alert-editor" style={{ marginTop: "var(--space-6)" }} onSubmit={save} onChange={() => setPreview("")}>
      <div className="alert-editor-heading">
        <h2 className="t-heading-lg">{existing ? "Edit alert" : "New alert"}</h2>
        <p className="t-caption">Choose what to monitor, then decide how you want to be notified.</p>
      </div>
      <fieldset className="alert-editor-section">
        <legend>Alert details</legend>
        <div className="alert-form-grid">
        <label className="t-caption">
          Type
          <select className="text-input" value={kind} onChange={e => {setKind(e.target.value); setThreshold(e.target.value === "freshness" ? 90 : e.target.value === "quality_score_drop" ? 10 : e.target.value === "size_spike" ? 50 : 25); setPreview("");}} style={{ display: "block" }}>
            {kinds.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="t-caption">
          Title
          <input className="text-input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional name for this alert" />
        </label>
        </div>
      </fieldset>
      <fieldset className="alert-editor-section">
        <legend>Scope and condition</legend>
        <p className="t-caption">Leave the layer and schema blank to monitor the whole connection.</p>
        <div className="alert-form-grid">
        <label className="t-caption">
          Target layer (optional)
          <input className="text-input" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="All layers" />
        </label>
        <label className="t-caption">Schema (optional)<input className="text-input" value={schema} onChange={e => setSchema(e.target.value)} placeholder="All schemas" /></label>
        {["row_count_drop", "size_spike", "freshness", "quality_score_drop"].includes(kind) && <label className="t-caption">{kind === "freshness" ? "Days since last update" : kind === "quality_score_drop" ? "Score drop (points)" : "Change threshold (%)"}<input className="text-input" type="number" min={kind === "freshness" || kind === "quality_score_drop" ? 1 : .01} max={kind === "freshness" ? 36500 : kind === "size_spike" ? 100000 : 100} step="any" value={threshold} onChange={e => setThreshold(Number(e.target.value))} required /></label>}
        {kind === "specific_user" && (
          <label className="t-caption">
            User
            <input className="text-input" value={user} onChange={(e) => setUser(e.target.value)} required style={{ display: "block" }} />
          </label>
        )}
        {kind === "banned_value" && (
          <>
            <label className="t-caption">
              Field
              <input className="text-input" value={field} onChange={(e) => setField(e.target.value)} required style={{ display: "block" }} />
            </label>
            <label className="t-caption">
              Operator
              <select className="text-input" value={operator} onChange={(e) => setOperator(e.target.value)} style={{ display: "block" }}>
                <option value="gt">greater than</option>
                <option value="gte">at least</option>
                <option value="lt">less than</option>
                <option value="lte">at most</option>
                <option value="eq">equals</option>
                <option value="ne">not equals</option>
                <option value="is_null">is empty</option>
                <option value="is_not_null">is not empty</option>
              </select>
            </label>
            {operator !== "is_null" && operator !== "is_not_null" && (
              <label className="t-caption">
                Value
                <input className="text-input" value={value} onChange={(e) => setValue(e.target.value)} required style={{ display: "block" }} />
              </label>
            )}
          </>
        )}
        {kind === "layer_presence" && (
          <label className="t-caption">
            When
            <select className="text-input" value={presence} onChange={(e) => setPresence(e.target.value)} style={{ display: "block" }}>
              <option value="either">added or dropped</option>
              <option value="added">added</option>
              <option value="dropped">dropped</option>
            </select>
          </label>
        )}
        </div>
      </fieldset>
      <fieldset className="alert-editor-section">
        <legend>Delivery</legend>
        <div className="alert-form-grid">
        <label className="t-caption">
          Notify
          <select className="text-input" value={notify} onChange={(e) => setNotify(e.target.value)} style={{ display: "block" }}>
            <option value="log">Write to log</option>
            <option value="webhook">Webhook</option>
            <option value="email">Email</option>
            <option value="slack">Slack</option>
            <option value="teams">Teams</option>
          </select>
        </label>
        {notify === "webhook" && (
          <label className="t-caption">
            Webhook URL
            <input className="text-input" type="url" value={webhook} placeholder={existing?.config.webhook_ref ? "Saved - leave blank to keep it" : ""} onChange={(e) => setWebhook(e.target.value)} style={{ display: "block" }} />
          </label>
        )}
        {notify === "email" && (
          <label className="t-caption">
            Recipient email address(es), comma-separated
            <input className="text-input" value={emailRecipients} onChange={(e) => setEmailRecipients(e.target.value)} required style={{ display: "block" }} />
          </label>
        )}
        </div>
        <p className="t-caption">Configure SMTP and saved chat channels in Settings. Preview evaluates the condition without sending a notification.</p>
      </fieldset>
      <p className="t-caption alert-editor-note">Comparison alerts need a previous scan. Freshness skips unknown update dates. Banned-value checks read bounded source samples for a selected layer and recorded after-values.</p>
      <div className="form-actions alert-editor-actions"><button type="submit" disabled={saving} className="button-primary-dark"><Ico t={saving ? "Saving…" : existing ? "Save alert" : "Create alert"} /></button><button type="button" className="button-secondary-outline" disabled={saving} onClick={async () => {setSaving(true); setPreview(""); try {const response = await fetch(`/api/connections/${connectionId}/alerts/preview`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body())}); const result = await response.json(); if (!response.ok) throw Error(result.detail); setPreview(`${result.matches.length} matches. ${result.matches.map((m: {message: string}) => m.message).join(" ")} ${result.message}${result.baseline_available ? "" : " No comparison baseline yet."}`);} catch (e) {onError(e instanceof Error ? e.message : "Preview failed.");} finally {setSaving(false);}}}><Ico t="Preview without sending" /></button>{existing && <button type="button" className="button-secondary-outline" onClick={onDone}><Ico t="Cancel edit" /></button>}</div>
      {preview && <p role="status" className="search-plan">{preview}</p>}
    </form>
  );
}

function conditionSummary(rule: AlertRule): string {
  const cfg = rule.config;
  if (rule.kind === "specific_user") return `user ${cfg.user ?? ""}`.trim();
  if (rule.kind === "banned_value") {
    return `${cfg.field ?? ""} ${cfg.operator ?? ""} ${cfg.value ?? ""}`.trim();
  }
  if (rule.kind === "layer_presence") return String(cfg.presence ?? "added or dropped");
  if (rule.kind === "row_count_drop") return `At least ${Number(cfg.threshold_share ?? .25) * 100}% fewer rows`;
  if (rule.kind === "freshness") return `No update in ${cfg.threshold_days ?? 90} days`;
  if (rule.kind === "quality_score_drop") return `Score down ${cfg.threshold_points ?? 10}+ points`;
  if (rule.kind === "size_spike") return `Size up at least ${Number(cfg.threshold_share ?? .5) * 100}%`;
  if (rule.kind === "mass_change") return "mass delete or edit";
  if (rule.kind === "schema_change") return "column add or remove";
  return " - ";
}

export default Alerts;
