/** FSD §14: status badge  -  color is never the only signal (FSD §16), so
 * every badge carries a text label too. */
function StatusBadge({ kind, label }: { kind: "good" | "warning" | "danger" | "info" | "neutral"; label: string }) {
  return <span className={`status-badge ${kind}`}>{label}</span>;
}

export default StatusBadge;
