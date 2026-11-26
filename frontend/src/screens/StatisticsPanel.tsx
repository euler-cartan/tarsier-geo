import { Ico } from "../components/Icon";
import { useEffect, useMemo, useState } from "react";
import { CachedItem, ColumnStats, getItemStats, scanItemStats, StatsRow, TableStats } from "../api";
import AiQueryBox, { FlagMap, RowsTable } from "../components/AiQueryBox";
import ColumnHistogram from "../components/ColumnHistogram";
import StatusBadge from "../components/StatusBadge";
import { ErrorState, LoadingState } from "../components/States";

const EMPTY_WARNING = 0.2;
const MAX_FULL_STATS_ROWS = 20_000;
const FULL_STATS_UNAVAILABLE = "Full statistics are not available for tables this large in this release. Sample statistics are shown and labelled.";
const EMPTY_TABLE = "This table has no rows";
const UNKNOWN_TABLE_SIZE = "Full statistics were not run because the table size could not be determined.";
const LARGE_TABLE_NO_SAMPLE = "Full statistics are not available for tables this large in this release. No sample statistics are available yet.";

export type FlagKey = "messy" | "out_of_range" | "duplicates" | "map_outliers" | "null_geometry";

/** FSD §8 / DVS §7 Statistics tab for one vector or tabular item. */
function StatisticsPanel({ connectionId, item, initialFlag }: { connectionId: string; item: CachedItem; initialFlag?: FlagKey | null }) {
  const [stats, setStats] = useState<TableStats | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningFull, setRunningFull] = useState(false);
  const [justFull, setJustFull] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<string>("name");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [flag, setFlag] = useState<FlagKey | null>(initialFlag ?? null);

  useEffect(() => setFlag(initialFlag ?? null), [initialFlag]);

  function load() {
    setLoading(true);
    getItemStats(connectionId, item.schema, item.name)
      .then((body) => {
        setStats(body);
        setMissing(false);
        setError(null);
      })
      .catch((err) => {
        setStats(null);
        if (String(err.message).includes("haven't been run")) setMissing(true);
        else setError(err.message);
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [connectionId, item.schema, item.name]);

  async function run(full: boolean) {
    setRunning(true);
    setRunningFull(full);
    setError(null);
    try {
      await scanItemStats(connectionId, item.schema, item.name, full);
      load();
      if (full) {
        setJustFull(true);
        window.setTimeout(() => setJustFull(false), 4000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run statistics.");
    } finally {
      setRunning(false);
      setRunningFull(false);
    }
  }

  const sorted = useMemo(() => {
    if (!stats) return [];
    const rows = [...stats.columns];
    rows.sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
      return String(av ?? "").localeCompare(String(bv ?? "")) * sortDir;
    });
    return rows;
  }, [stats, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortKey(key);
      setSortDir(1);
    }
  }

  const flagRows: Record<FlagKey, StatsRow[]> = {
    messy: stats?.messy_category_rows ?? [],
    out_of_range: stats?.out_of_range_rows ?? [],
    duplicates: stats?.duplicate_rows ?? [],
    map_outliers: stats?.map_outlier_rows ?? [],
    null_geometry: stats?.null_geometry_rows ?? [],
  };

  return (
    <div>
      <AiQueryBox connectionId={connectionId} schema={item.schema} name={item.name} />

      {loading && <LoadingState label="Loading statistics" rows={2} />}
      {!loading && item.row_count === 0 && <p className="t-caption" role="status">{EMPTY_TABLE}</p>}
      {!loading && !stats && item.row_count !== null && item.row_count > MAX_FULL_STATS_ROWS && <p className="t-caption" role="status">{LARGE_TABLE_NO_SAMPLE}</p>}
      {!loading && !stats && item.row_count === null && <p className="t-caption" role="status">{UNKNOWN_TABLE_SIZE}</p>}

      {!loading && missing && item.row_count !== 0 && (
        <p className="t-caption" style={{ marginTop: "var(--space-5)" }}>
          No statistics yet.{" "}
          <button type="button" className="button-secondary-outline" onClick={() => run(false)} disabled={running}><Ico t="Run now" /></button>
        </p>
      )}

      {error && <ErrorState message={error} onRetry={load} />}

      {stats && (
        <>
          <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", margin: "var(--space-5) 0", flexWrap: "wrap" }}>
            {stats.is_sample && (
              <span className="t-caption" style={{ background: "var(--hairline)", borderRadius: 999, padding: "2px 10px" }}>
                Based on a sample ({stats.sampled_row_count.toLocaleString()} rows); all statistics below are sample-based, not a full check
              </span>
            )}
            <button type="button" className="button-secondary-outline" onClick={() => run(false)} disabled={running}><Ico t="Run now" /></button>
            {stats.is_sample && item.row_count !== null && item.row_count > 0 && item.row_count <= MAX_FULL_STATS_ROWS && (
              <button type="button" className="button-secondary-outline" onClick={() => run(true)} disabled={running}><Ico t="Run full check" /></button>
            )}
            {stats.is_sample && item.row_count !== null && item.row_count > MAX_FULL_STATS_ROWS && <p className="t-caption" role="status">{FULL_STATS_UNAVAILABLE}</p>}
            {stats.is_sample && item.row_count === null && <p className="t-caption" role="status">{UNKNOWN_TABLE_SIZE}</p>}
            {runningFull && stats.is_sample && <p className="t-caption" role="status">Checking all rows; the current sample remains visible while this runs.</p>}
            {justFull && !stats.is_sample && (
              <span className="t-caption" role="status">
                Now showing full data
              </span>
            )}
          </div>

          <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
            <FlagButton
              label="Messy categories"
              count={flagRows.messy.length}
              active={flag === "messy"}
              onClick={() => setFlag(flag === "messy" ? null : "messy")}
            />
            <FlagButton
              label="Out of range"
              count={flagRows.out_of_range.length}
              active={flag === "out_of_range"}
              onClick={() => setFlag(flag === "out_of_range" ? null : "out_of_range")}
            />
            <FlagButton
              label="Duplicates"
              count={flagRows.duplicates.length}
              active={flag === "duplicates"}
              onClick={() => setFlag(flag === "duplicates" ? null : "duplicates")}
            />
            {stats.spatial_outlier_count != null && (
              <FlagButton
                label="Map outliers"
                count={stats.spatial_outlier_count}
                active={flag === "map_outliers"}
                onClick={() => setFlag(flag === "map_outliers" ? null : "map_outliers")}
              />
            )}
            {stats.null_geometry_count != null && (
              <FlagButton
                label="Null geometry"
                count={stats.null_geometry_count}
                active={flag === "null_geometry"}
                onClick={() => setFlag(flag === "null_geometry" ? null : "null_geometry")}
              />
            )}
          </div>

          {flag && (
            <div className="card" style={{ marginBottom: "var(--space-5)" }}>
              <h3 className="t-heading-lg" style={{ marginTop: 0 }}>
                Matching rows
              </h3>
              <RowsTable rows={flagRows[flag]} />
              {(flag === "map_outliers" || flag === "null_geometry") && <FlagMap rows={flagRows[flag]} />}
            </div>
          )}

          <div className="table-scroll"><table className="data-table column-statistics-table">
            <thead>
              <tr>
                <Header label="Column" onClick={() => toggleSort("name")} />
                <Header label="Type" onClick={() => toggleSort("is_numeric")} />
                <Header label="Min" onClick={() => toggleSort("minimum")} />
                <Header label="Max" onClick={() => toggleSort("maximum")} />
                <Header label="Average" onClick={() => toggleSort("average")} />
                <Header label="Empty" onClick={() => toggleSort("empty_count")} />
                <Header label="Unique" onClick={() => toggleSort("unique_count")} />
                <th>Top values</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((col) => (
                <ColumnRows
                  key={col.name}
                  col={col}
                  sampled={stats.sampled_row_count}
                  expanded={expanded === col.name}
                  onToggle={() => setExpanded(expanded === col.name ? null : col.name)}
                />
              ))}
            </tbody>
          </table></div>
        </>
      )}
    </div>
  );
}

function Header({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <th>
      <button type="button" onClick={onClick} className="t-caption" style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", padding: 0, minHeight: 40 }}>
        {label}
      </button>
    </th>
  );
}

function FlagButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" onClick={onClick} style={{ background: "none", border: "none", cursor: "pointer", padding: 0, minHeight: 40 }}>
      <StatusBadge kind={active ? "info" : count > 0 ? "warning" : "neutral"} label={`${label}: ${count}`} />
    </button>
  );
}

function ColumnRows({
  col,
  sampled,
  expanded,
  onToggle,
}: {
  col: ColumnStats;
  sampled: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const emptyShare = sampled ? col.empty_count / sampled : 0;
  const barColor = emptyShare >= EMPTY_WARNING ? "var(--status-warning)" : "var(--ink-faint)";
  return (
    <>
      <tr
        onClick={onToggle}
        onKeyDown={(event) => {
          if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            onToggle();
          }
        }}
        tabIndex={0}
        aria-expanded={expanded}
      >
        <td>{col.name}</td>
        <td>{col.is_numeric ? "Number" : "Text"}</td>
        <td>{fmt(col.minimum)}</td>
        <td>{fmt(col.maximum)}</td>
        <td>{col.average == null ? " - " : Number(col.average).toPrecision(4)}</td>
        <td>
          {col.empty_count}
          <span
            style={{
              display: "inline-block",
              width: 48,
              height: 6,
              marginLeft: 8,
              background: "var(--hairline)",
              borderRadius: 4,
              verticalAlign: "middle",
            }}
          >
            <span style={{ display: "block", width: `${Math.min(emptyShare, 1) * 100}%`, height: "100%", background: barColor, borderRadius: 4 }} />
          </span>
        </td>
        <td>{col.unique_count}</td>
        <td className="t-caption">
          {col.top_values.slice(0, 3).map(([v, n]) => (
            <div key={v} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{v}</span>
              <span
                style={{
                  display: "inline-block",
                  height: 6,
                  width: `${Math.max(4, Math.min(100, sampled ? n / sampled * 100 : 0))}%`,
                  maxWidth: 84, flexShrink: 0,
                  background: "var(--primary)",
                  borderRadius: 4,
                }}
              />
            </div>
          ))}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8}>
            <ColumnHistogram column={col} />
          </td>
        </tr>
      )}
    </>
  );
}

function fmt(value: string | number | null) {
  if (value == null) return " - ";
  return String(value);
}

export default StatisticsPanel;
