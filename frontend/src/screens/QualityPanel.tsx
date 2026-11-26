import { Ico } from "../components/Icon";
import { ChangeEvent, FormEvent, useEffect, useState, useRef } from "react";
import {
  CachedItem,
  createQualityRule,
  deleteQualityRule,
  getItemQuality,
  QualityCheckResult,
  QualityReport,
  QualityRule,
  saveQualityBoundary,
  scanItemQuality,
  updateQualityRule,
} from "../api";
import { ErrorState, LoadingState } from "../components/States";
import { FlagMap, RowsTable } from "../components/AiQueryBox";
import StatusBadge from "../components/StatusBadge";
import { useAi } from "../shell/AiContext";

const LABELS: Record<string, string> = {
  validity: "Geometry validity",
  overlaps: "Topology  -  overlaps",
  slivers: "Topology  -  slivers",
  gaps: "Topology  -  gaps",
  dangles: "Topology  -  dangles",
  completeness: "Completeness",
  projection: "Projection",
  boundary: "Boundary",
  custom_rules: "Custom rules",
};

const ORDER = Object.keys(LABELS);

/** FSD §9 / DVS §8 Quality tab. Each check scans on its own (TRS-039). */
function QualityPanel({ connectionId, item, onChecked }: { connectionId: string; item: CachedItem; onChecked?: () => void }) {
  const ai = useAi();
  const [report, setReport] = useState<QualityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<Set<string>>(new Set());
  const [suiteRunning, setSuiteRunning] = useState(false);
  const [suiteStatus, setSuiteStatus] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showMap, setShowMap] = useState<string | null>(null);

  function applyReport(body: QualityReport) {
    setReport(body);
    setError(null);
  }

  function load() {
    setError(null);
    getItemQuality(connectionId, item.schema, item.name, item.kind)
      .then(applyReport)
      .catch((err) => setError(err.message));
  }

  useEffect(load, [connectionId, item.schema, item.name, item.kind]);

  async function runCheck(checkId: string, full = false) {
    setRunning((prev) => new Set(prev).add(checkId));
    try {
      const result = await scanItemQuality(connectionId, item.schema, item.name, checkId, full);
      setReport((prev) =>
        prev ? { ...prev, checks: { ...prev.checks, [checkId]: result } } : prev
      );

    } catch (err) {
      setError(previous => [previous, err instanceof Error ? err.message : "Could not run that quality check."].filter(Boolean).join(" "));
    } finally {
      setRunning((prev) => {
        const next = new Set(prev);
        next.delete(checkId);
        return next;
      });
    }
  }

  async function runAll() {
    if (!report || suiteRunning) return;
    setSuiteRunning(true); setError(null);
    try {
      const ids = Object.keys(report.checks);
      for (let i=0; i<ids.length; i++) {setSuiteStatus(`${i+1} of ${ids.length}: ${LABELS[ids[i]] || ids[i]}`); await runCheck(ids[i], true);}
      setSuiteStatus("Checks finished. Review the results and any errors below.");
      onChecked?.();
    } finally {setSuiteRunning(false);}
  }

  async function onBoundary(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.currentTarget.value;
    const [boundarySchema, boundaryName] = value ? value.split("\t") : [null, null];
    try {
      await saveQualityBoundary(connectionId, item.schema, item.name, boundarySchema, boundaryName);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the boundary layer.");
    }
  }

  if (error && !report) {
    return <ErrorState message={error} onRetry={() => { setError(null); load(); }} />;
  }
  if (!report) {
    return <LoadingState label="Loading quality checks" />;
  }

  const checks = ORDER.filter((id) => id in report.checks).map((id) => report.checks[id]);

  return (
    <div>
      <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-5)", flexWrap: "wrap" }}>
        <button type="button" className="button-primary-dark" onClick={runAll} disabled={suiteRunning}><Ico t={suiteRunning ? "Running checks…" : "Run checks now"} /></button>
        {suiteStatus && <p role="status" className="t-caption" aria-busy={suiteRunning}>{suiteStatus}</p>}
      </div>
      {error && (
        <p style={{ color: "var(--status-danger)" }} role="alert">
          {error}
        </p>
      )}

      {item.kind === "vector" && (
        <div className="card" style={{ marginBottom: "var(--space-5)" }}>
          <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
            Boundary
          </h2>
          <label className="t-caption">
            Expected area (another layer on this connection)
            <select
              className="text-input"
              style={{ display: "block", marginTop: "var(--space-2)", minWidth: 240 }}
              value={
                report.boundary_name != null
                  ? `${report.boundary_schema ?? ""}\t${report.boundary_name}`
                  : ""
              }
              onChange={onBoundary}
            >
              <option value="">None  -  check not applicable</option>
              {report.vector_layers.map((layer) => (
                <option key={`${layer.schema}.${layer.name}`} value={`${layer.schema}\t${layer.name}`}>
                  {layer.schema ? `${layer.schema}.` : ""}
                  {layer.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        {checks.map((check) => (
          <CheckRow
            key={check.check_id}
            check={check}
            running={running.has(check.check_id)}
            expanded={expanded === check.check_id}
            showingMap={showMap === check.check_id}
            onToggle={() => setExpanded(expanded === check.check_id ? null : check.check_id)}
            onShowMap={() => setShowMap(showMap === check.check_id ? null : check.check_id)}
            onExplain={() =>
              ai.show({
                job: "explain-quality",
                schema: item.schema,
                name: item.name,
                checkId: check.check_id,
              })
            }
          />
        ))}
      </div>

      <RulesManager
        connectionId={connectionId}
        item={item}
        rules={report.rules}
        columns={report.columns ?? []}
        onChanged={load}
        onError={setError}
      />
    </div>
  );
}

function CheckRow({
  check,
  running,
  expanded,
  showingMap,
  onToggle,
  onShowMap,
  onExplain,
}: {
  check: QualityCheckResult;
  running: boolean;
  expanded: boolean;
  showingMap: boolean;
  onToggle: () => void;
  onShowMap: () => void;
  onExplain: () => void;
}) {
  const passed = check.status === "good";
  const failed = check.status === "danger" || check.status === "warning";
  const failShare = failed ? 1 : 0;
  return (
    <div className="card">
      <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
        <button
          type="button"
          onClick={onToggle}
          className="t-body-md"
          style={{
            flex: 1,
            textAlign: "left",
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 0,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "var(--space-2)" }}>
            <span>{LABELS[check.check_id] ?? check.check_id}</span>
            <CheckBadge check={check} running={running} />
          </div>
          <div
            style={{
              height: 12,
              borderRadius: 999,
              overflow: "hidden",
              background: "var(--ink-faint)",
              display: "flex",
            }}
            className={running ? "quality-bar-running" : undefined}
          >
            {!running && check.status !== "never_run" && check.status !== "not_applicable" && (
              <>
                <div style={{ flex: passed ? 1 : 1 - failShare, background: check.is_sample ? "var(--ink-faint)" : "var(--status-good)" }} />
                {failed && <div style={{ flex: failShare, background: "var(--status-danger)" }} />}
              </>
            )}
          </div>
        </button>
        {failed && (
          <button type="button" className="button-secondary-outline" onClick={onExplain}><Ico t="Explain with AI" /></button>
        )}
      </div>
      {check.is_sample && check.status !== "never_run" && (
        <p style={{ margin: "var(--space-2) 0 0" }}>
          <span className="t-caption" style={{ background: "var(--hairline)", borderRadius: 999, padding: "2px 10px" }}>
            Based on a sample
          </span>
        </p>
      )}
      {check.message && (
        <p className="t-caption" style={{ marginBottom: 0 }}>
          {check.message}
        </p>
      )}
      {expanded && (
        <div style={{ marginTop: "var(--space-4)" }}>
          {check.fail_count > 0 && (
            <button type="button" className="button-secondary-outline" onClick={onShowMap}><Ico t={showingMap ? "Hide map" : "Show on map"} /></button>
          )}
          <RowsTable rows={check.failing_rows} />
          {showingMap && <FlagMap rows={check.failing_rows} />}
        </div>
      )}
    </div>
  );
}

function CheckBadge({ check, running }: { check: QualityCheckResult; running: boolean }) {
  if (running) return <StatusBadge kind="info" label="Running" />;
  if (check.status === "never_run") return <StatusBadge kind="neutral" label="Not yet run" />;
  if (check.status === "not_applicable") return <StatusBadge kind="neutral" label="Not applicable" />;
  if (check.is_sample && check.fail_count === 0) return <StatusBadge kind="neutral" label="none found in sample, not a full check" />;
  if (check.status === "good") return <StatusBadge kind="good" label="0 failed" />;
  return <StatusBadge kind="danger" label={`${check.fail_count} failed${check.is_sample ? " in sample" : ""}`} />;
}

function RulesManager({
  connectionId,
  item,
  rules,
  columns,
  onChanged,
  onError,
}: {
  connectionId: string;
  item: CachedItem;
  rules: QualityRule[];
  columns: { name: string; type: string }[];
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [kind, setKind] = useState("attribute");
  const [field, setField] = useState("");
  const [operator, setOperator] = useState("gt");
  const [value, setValue] = useState("");
  const [geometryType, setGeometryType] = useState("LineString");
  const review = useRef<HTMLDialogElement>(null);
  const [aiAuthored, setAiAuthored] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);

  async function save(event?: FormEvent, approved = false) {
    event?.preventDefault();
    if (aiAuthored && !approved) { review.current?.showModal(); return; }
    const body = {
      ai_authored: aiAuthored, review_approved: approved,
      kind,
      field,
      operator: kind === "geometry_type" ? "eq" : operator,
      value: kind === "attribute" && operator === "is_unique" ? null : value,
      geometry_type: kind === "geometry_type" ? geometryType : null,
    };
    try {
      if (editing) {
        await updateQualityRule(connectionId, editing, item.schema, item.name, body);
      } else {
        await createQualityRule(connectionId, item.schema, item.name, body);
      }
      review.current?.close();
      setAiAuthored(false);
      setEditing(null);
      setField("");
      setValue("");
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not save that rule.");
    }
  }

  return (
    <div className="card" style={{ marginTop: "var(--space-6)" }}>
      <h2 className="t-heading-lg" style={{ marginTop: 0 }}>
        Custom rules
      </h2>

      <div className="rule-ai-composer">
        <h3 className="t-heading-lg">Draft a rule with AI</h3><label className="t-caption">Describe the requirement<input className="text-input" value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Diameter must be positive" /></label>
        <button className="button-secondary-outline" disabled={drafting || !prompt.trim()} onClick={async () => {
          setDrafting(true);
          try {
            const response = await fetch(`/api/connections/${connectionId}/ai/chat`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job: "draft-rule", message: prompt, schema: item.schema, name: item.name})});
            const data = await response.json(); if (!response.ok) throw Error(data.detail || "Could not draft rule.");
            setKind(data.rule.kind); setField(data.rule.field); setOperator(data.rule.operator); setValue(data.rule.value ?? ""); setGeometryType(data.rule.geometry_type ?? "LineString"); setEditing(null); setAiAuthored(true);
            review.current?.showModal();
          } catch(e) {onError(e instanceof Error ? e.message : "Could not draft rule.");} finally {setDrafting(false);}
        }}><Ico t={drafting ? "Drafting…" : "Draft with AI"} /></button>
        <p className="t-caption">Uses your configured AI provider. External AI receives the rule description and available column names; no rows are sent.</p>
      </div>
      <dialog ref={review} className="review-dialog" aria-labelledby="rule-review-title">
        <h2 id="rule-review-title" className="t-display-md">Review before saving</h2><p>Tarsier never saves or runs anything from AI without your approval.</p>
        <p>{kind === "geometry_type" ? "When" : "Require"} {field} {operator} {value}{kind === "geometry_type" ? `: geometry must be ${geometryType}` : ""}</p>
        <button className="button-primary-dark" onClick={() => save(undefined, true)}><Ico t="Approve & save" /></button>{" "}
        <button className="button-secondary-outline" onClick={() => review.current?.close()}><Ico t="Edit first" /></button>{" "}
        <button className="button-secondary-outline" onClick={() => {review.current?.close(); setAiAuthored(false); setField(""); setValue("");}}><Ico t="Discard" /></button>
      </dialog>
      <ul style={{ paddingLeft: "var(--space-5)" }}>
        {rules.map((rule) => (
          <li key={rule.id} className="saved-rule">
            {rule.kind === "geometry_type"
              ? `When ${rule.field} ${rule.operator} ${rule.value}, geometry must be ${rule.geometry_type}`
              : `${rule.field} ${rule.operator} ${rule.value ?? ""}`}
            <button
              type="button"
              className="button-secondary-outline"
              style={{ marginLeft: "var(--space-3)" }}
              onClick={() => {
                setAiAuthored(false);
                setEditing(rule.id);
                setKind(rule.kind);
                setField(rule.field);
                setOperator(rule.operator);
                setValue(rule.value ?? "");
                setGeometryType(rule.geometry_type ?? "LineString");
              }}
            ><Ico t="Edit" /></button>
            <button
              type="button"
              className="button-secondary-outline"
              style={{ marginLeft: "var(--space-2)" }}
              onClick={async () => {
                try {
                  await deleteQualityRule(connectionId, rule.id);
                  onChanged();
                } catch (err) {
                  onError(err instanceof Error ? err.message : "Could not delete that rule.");
                }
              }}
            ><Ico t="Delete" /></button>
          </li>
        ))}
      </ul>
      <form onSubmit={save} className="rule-form">
        <label className="t-caption">
          Kind
          <select className="text-input" value={kind} onChange={(e) => setKind(e.target.value)} style={{ display: "block" }}>
            <option value="attribute">Attribute</option>
            {item.kind === "vector" && <option value="geometry_type">Geometry type</option>}
          </select>
        </label>
        <label className="t-caption">
          Field
          <input className="text-input" value={field} onChange={(e) => setField(e.target.value)} required style={{ display: "block" }} />
        </label>
        {kind === "attribute" ? (
          <>
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
                <optgroup label="Compare to another column">
                  <option value="column_gt">greater than column</option>
                  <option value="column_gte">at least column</option>
                  <option value="column_lt">less than column</option>
                  <option value="column_lte">at most column</option>
                  <option value="column_eq">equals column</option>
                  <option value="column_ne">not equal to column</option>
                </optgroup>
                <option value="matches">matches text pattern</option>
                <option value="not_matches">does not match text pattern</option>
                <option value="is_unique">is unique</option>
              </select>
            </label>
            {operator !== "is_unique" && <label className="t-caption">
              {operator.startsWith("column_") ? "Compare column" : operator.includes("matches") ? "Regular expression" : "Value"}
              {operator.startsWith("column_") ? <select className="text-input" value={value} onChange={(e) => setValue(e.target.value)} required style={{ display: "block" }}>
                <option value="">Select a column</option>
                {columns.map(col => <option key={col.name} value={col.name}>{col.name} ({col.type})</option>)}
              </select> : <input className="text-input" value={value} onChange={(e) => setValue(e.target.value)} style={{ display: "block" }} />}
              {operator.startsWith("column_") && !columns.length && <span>Run a check to load this table’s columns.</span>}
            </label>}
          </>
        ) : (
          <>
            <label className="t-caption">
              Equals
              <input className="text-input" value={value} onChange={(e) => setValue(e.target.value)} required style={{ display: "block" }} />
            </label>
            <label className="t-caption">
              Geometry must be
              <select className="text-input" value={geometryType} onChange={(e) => setGeometryType(e.target.value)} style={{ display: "block" }}>
                <option>Point</option>
                <option>LineString</option>
                <option>Polygon</option>
                <option>MultiPoint</option>
                <option>MultiLineString</option>
                <option>MultiPolygon</option>
              </select>
            </label>
          </>
        )}
        <button type="submit" className="button-secondary-outline"><Ico t={editing ? "Save rule" : "Add rule"} /></button>
      </form>
    </div>
  );
}

export default QualityPanel;
