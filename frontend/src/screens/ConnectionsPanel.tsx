import { Ico } from "../components/Icon";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CachedItem, FlowchartLink, getFlowchart } from "../api";
import StatusBadge from "../components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

const KIND_LABEL: Record<FlowchartLink["kind"], string> = { official: "Official", guessed: "Guessed", user: "Added by you" };

function itemUrl(connectionId: string, schema: string, name: string): string {
  return `/connections/${connectionId}/items?${new URLSearchParams({ schema, name })}`;
}

/** FSD §7  -  this item's links from the flowchart (FSD §12), shown inline. */
function ConnectionsPanel({ connectionId, item }: { connectionId: string; item: CachedItem }) {
  const [links, setLinks] = useState<FlowchartLink[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const here = (cid: string | undefined, schema: string, name: string) =>
    (cid ?? connectionId) === connectionId && schema === item.schema && name === item.name;

  function load() {
    setError(null);
    getFlowchart(connectionId)
      .then((graph) =>
        setLinks(
          graph.links.filter(
            (l) =>
              here(l.source_connection_id, l.source_schema, l.source_name) ||
              here(l.target_connection_id, l.target_schema, l.target_name)
          )
        )
      )
      .catch((err) => setError(err.message));
  }

  useEffect(load, [connectionId, item.schema, item.name]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!links) return <LoadingState label="Loading connections" rows={2} />;

  const flowchartLink = (
    <Link to={`/connections/${connectionId}/flowchart`} className="button-secondary-outline"><Ico t="Open the full flowchart" /></Link>
  );

  if (links.length === 0) {
    return (
      <EmptyState title="No connections found for this item" action={flowchartLink}>
        Connections appear once the flowchart has been scanned. You can also add one by hand there.
      </EmptyState>
    );
  }

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", flexWrap: "wrap" }}>
        <h2 className="t-heading-lg" style={{ margin: 0 }}>Connections</h2>
        {flowchartLink}
      </div>
      <table className="data-table" style={{ marginTop: "var(--space-4)" }}>
        <thead>
          <tr>
            <th>Connected item</th>
            <th>This item's column</th>
            <th>Their column</th>
            <th>Type</th>
          </tr>
        </thead>
        <tbody>
          {links.map((l) => {
            const outgoing = here(l.source_connection_id, l.source_schema, l.source_name);
            const other = outgoing
              ? { cid: l.target_connection_id ?? connectionId, schema: l.target_schema, name: l.target_name, column: l.target_column, mine: l.source_column }
              : { cid: l.source_connection_id ?? connectionId, schema: l.source_schema, name: l.source_name, column: l.source_column, mine: l.target_column };
            return (
              <tr key={l.id}>
                <td>
                  <Link to={itemUrl(other.cid, other.schema, other.name)} style={{ color: "var(--primary)" }}>
                    {other.name}
                  </Link>
                  {other.cid !== connectionId && <span className="t-caption"> in another connection</span>}
                </td>
                <td>{other.mine}</td>
                <td>{other.column}</td>
                <td>
                  <StatusBadge kind={l.kind === "guessed" ? "warning" : "info"} label={l.kind === "guessed" ? "Guessed ?" : KIND_LABEL[l.kind]} />
                  {l.sample_based && <span className="t-caption"> sample-based</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default ConnectionsPanel;
