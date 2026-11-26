import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { CachedItem, getItemPreview, scanItemPreview, TabularPreview } from "../api";
import { formatRowCount } from "../format";

/** FSD §7  -  Tabular overview: row count, column schema, and a sample rows table. */
function TabularPanel({ connectionId, item }: { connectionId: string; item: CachedItem }) {
  const [preview, setPreview] = useState<TabularPreview | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  function load() {
    setLoading(true);
    return getItemPreview(connectionId, item.schema, item.name)
      .then((body) => {
        setPreview(body);
        setMissing(false);
        setError(null);
      })
      .catch((err) => {
        setPreview(null);
        if (String(err.message).includes("haven't been loaded")) setMissing(true);
        else setError(err.message);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [connectionId, item.schema, item.name]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      await scanItemPreview(connectionId, item.schema, item.name);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sample rows.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: "var(--space-6)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <h2 className="t-heading-lg" style={{ margin: 0 }}>Table contents</h2>
        <span className="t-caption">{formatRowCount(item.row_count, item.row_count_is_estimate, item.row_count_is_capped)} rows</span>
        <button type="button" className="button-secondary-outline" onClick={run} disabled={running}><Ico t={preview ? "Refresh sample rows" : "Load sample rows"} /></button>
      </div>

      {loading && <div className="skeleton" style={{ height: 160, marginTop: "var(--space-4)" }} aria-label="Loading sample rows" />}

      {!loading && missing && (
        <p className="t-caption" style={{ marginTop: "var(--space-4)" }}>
          No sample rows loaded yet. Use "Load sample rows" to read the first few rows and the column list.
        </p>
      )}

      {error && (
        <p style={{ color: "var(--status-danger)" }} role="alert">
          {error}{" "}
          <button type="button" className="button-secondary-outline" onClick={() => load()}><Ico t="Retry" /></button>
        </p>
      )}

      {preview && (
        <>
          <h3 className="t-heading-lg">Columns</h3>
          <ul style={{ listStyle: "none", padding: 0, display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
            {preview.columns.map((c) => (
              <li key={c.name} className="t-caption" style={{ background: "var(--hairline)", borderRadius: 999, padding: "2px 10px" }}>
                {c.name} · {c.type}
              </li>
            ))}
          </ul>
          <h3 className="t-heading-lg">Sample rows</h3>
          {preview.rows.length === 0 ? (
            <p className="t-caption">This table has no rows.</p>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    {preview.columns.map((c) => (
                      <th key={c.name} className="t-caption" style={{ textAlign: "left" }}>
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, i) => (
                    <tr key={i}>
                      {preview.columns.map((c) => (
                        <td key={c.name}>
                          {row[c.name] === null || row[c.name] === undefined ? (
                            <span style={{ color: "var(--ink-faint)" }}>empty</span>
                          ) : (
                            String(row[c.name])
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default TabularPanel;
