import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { OverviewLayerRow } from "../api";
import { formatBytes, formatDate, formatRowCount } from "../format";
import HealthRing from "./HealthRing";
import StatusBadge from "./StatusBadge";

const KIND_LABEL: Record<string, string> = { vector: "Vector", raster: "Raster", tabular: "Table" };

type SortKey = "name" | "kind" | "row_count" | "size_bytes";

/** FSD §6 layer list table. */
function LayerTable({ layers, projectionFilter }: { layers: OverviewLayerRow[]; projectionFilter: number | null }) {
  const { connectionId } = useParams<{ connectionId: string }>();
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDesc, setSortDesc] = useState(false);

  const filtered = projectionFilter === null ? layers : layers.filter((l) => l.srid === projectionFilter);

  const sorted = [...filtered].sort((a, b) => {
    const av = a[sortKey] ?? -Infinity;
    const bv = b[sortKey] ?? -Infinity;
    const cmp = typeof av === "string" ? av.localeCompare(String(bv)) : Number(av) - Number(bv);
    return sortDesc ? -cmp : cmp;
  });

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDesc((d) => !d);
    else {
      setSortKey(key);
      setSortDesc(false);
    }
  }

  if (layers.length === 0) {
    return <p className="t-caption">No layers found.</p>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th onClick={() => toggleSort("name")} style={{ cursor: "pointer" }}>Name</th>
          <th onClick={() => toggleSort("kind")} style={{ cursor: "pointer" }}>Type</th>
          <th onClick={() => toggleSort("row_count")} style={{ cursor: "pointer" }}>Rows</th>
          <th onClick={() => toggleSort("size_bytes")} style={{ cursor: "pointer" }}>Size</th>
          <th>Last changed</th>
          <th>Projection</th>
          <th>Index</th>
          <th>Quality</th>
          <th>Health</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((layer) => (
          <tr
            key={`${layer.schema}:${layer.name}`}
            onClick={() => navigate(`/connections/${connectionId}/items?schema=${encodeURIComponent(layer.schema)}&name=${encodeURIComponent(layer.name)}`)}
          >
            <td>
              <Link to={`/connections/${connectionId}/items?schema=${encodeURIComponent(layer.schema)}&name=${encodeURIComponent(layer.name)}`}>{layer.name}</Link>
              {layer.readable === false && <StatusBadge kind="neutral" label="no permission" />}
              {layer.is_stale && (
                <span className="t-micro" style={{ marginLeft: "var(--space-3)" }}>
                  <StatusBadge kind="neutral" label="Stale" />
                </span>
              )}
              {layer.is_heavy && (
                <span className="t-micro" style={{ marginLeft: "var(--space-3)" }}>
                  <StatusBadge kind="warning" label="Heavy" />
                </span>
              )}
            </td>
            <td>{KIND_LABEL[layer.kind] ?? layer.kind}</td>
            <td>{formatRowCount(layer.row_count, layer.row_count_is_estimate, layer.row_count_is_capped)}</td>
            <td>{formatBytes(layer.size_bytes)}</td>
            <td>{layer.last_modified ? formatDate(layer.last_modified) : "Not tracked yet"}</td>
            <td>{layer.srid ? `EPSG:${layer.srid}` : "Not available"}</td>
            <td>
              {layer.has_index === null ? (
                <StatusBadge kind="neutral" label="Not available" />
              ) : layer.has_index ? (
                <StatusBadge kind="good" label="✓" />
              ) : (
                <StatusBadge kind="warning" label="✗" />
              )}
            </td>
            <td>
              <StatusBadge kind={layer.health_is_sample || layer.health_components?.quality == null ? "neutral" : layer.health_components.quality >= 80 ? "good" : layer.health_components.quality >= 50 ? "warning" : "danger"} label={layer.health_components?.quality == null ? "Not yet checked" : `${layer.health_components.quality}% passed${layer.health_is_sample ? " (sample-based; not a full check)" : ""}`} />
            </td>
            <td>
              <HealthRing isSample={layer.health_is_sample} score={layer.health_score} components={layer.health_components} size="small" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default LayerTable;
