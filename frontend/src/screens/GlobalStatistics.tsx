import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ConnectionStatisticsLayer, getConnectionStatistics } from "../api";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

type Flag = "messy" | "duplicates" | "out_of_range" | "map_outliers" | "null_geometry";

/** FSD §8.1: cached cross-layer flag counts, with details kept on each layer. */
function GlobalStatistics() {
  const { connectionId } = useParams<{ connectionId: string }>();
  const [layers, setLayers] = useState<ConnectionStatisticsLayer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    if (!connectionId) return;
    setError(null);
    getConnectionStatistics(connectionId)
      .then((result) => {
        setLayers(result.layers);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load connection statistics."));
  }

  useEffect(load, [connectionId]);

  if (!connectionId) return null;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (layers === null) return <LoadingState label="Loading statistics" />;

  return (
    <div>
      <h1 className="t-display-lg">Statistics</h1>
      <p className="t-caption">Flag counts across this connection. Open a layer's Statistics tab for its matching rows and details.</p>
      {layers.length === 0 ? (
        <EmptyState
          title="No layers have been scanned yet"
          action={<Link to={`/connections/${connectionId}/overview`} className="button-primary-dark"><Ico t="Run a check on the Overview" /></Link>}
        >
          Statistics appear here once the Overview has scanned this connection.
        </EmptyState>
      ) : (
        <div className="table-scroll"><table className="data-table global-statistics-table">
          <thead>
            <tr>
              <th>Layer</th><th>Messy categories</th><th>Duplicates</th><th>Out of range</th><th>Map outliers</th><th>Null geometry</th>
            </tr>
          </thead>
          <tbody>
            {layers.map((layer) => (
              <tr key={`${layer.schema}.${layer.name}`}>
                <td><Link to={itemUrl(connectionId, layer)} style={{ color: "var(--primary)" }}>{layer.name}</Link><div className="t-micro">{layer.schema || layer.kind}</div>{layer.is_sample && <div className="t-micro">Sample-based ({layer.sampled_row_count?.toLocaleString()} rows); all values in this row are from the sample</div>}</td>
                {layer.is_scanned ? (
                  <>
                    <td><CountLink count={layer.messy_category_count} connectionId={connectionId} layer={layer} flag="messy" /></td>
                    <td><CountLink count={layer.duplicate_count} connectionId={connectionId} layer={layer} flag="duplicates" /></td>
                    <td><CountLink count={layer.out_of_range_count} connectionId={connectionId} layer={layer} flag="out_of_range" /></td>
                    <td><CountLink count={layer.map_outlier_count} connectionId={connectionId} layer={layer} flag="map_outliers" /></td>
                    <td><CountLink count={layer.null_geometry_count} connectionId={connectionId} layer={layer} flag="null_geometry" /></td>
                  </>
                ) : (
                  <td colSpan={5} className="t-caption">{layer.kind === "raster" ? "Statistics are not available for raster layers." : <>Not scanned or unavailable for this layer. <Link to={itemUrl(connectionId, layer, "statistics")} style={{ color: "var(--primary)" }}>Open Statistics</Link></>}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

function CountLink({ count, connectionId, layer, flag }: { count: number | null; connectionId: string; layer: ConnectionStatisticsLayer; flag: Flag }) {
  if (count === null) return <span className="t-caption" style={{ color: "var(--ink-faint)" }}> - </span>;
  return <Link to={itemUrl(connectionId, layer, "statistics", flag)} style={{ color: "var(--primary)" }}>{count.toLocaleString()}</Link>;
}

function itemUrl(connectionId: string, layer: ConnectionStatisticsLayer, tab?: string, flag?: Flag): string {
  const query = new URLSearchParams({ schema: layer.schema, name: layer.name });
  if (tab) query.set("tab", tab);
  if (flag) query.set("flag", flag);
  return `/connections/${connectionId}/items?${query.toString()}`;
}

export default GlobalStatistics;
