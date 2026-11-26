/**
 * FSD §15 / DVS §15: loading must be a skeleton shaped like the eventual
 * content, not a blank area or a bare spinner. Mirrors Overview's real
 * layout  -  header, 4 stat cards, 2 content cards, and a table  -  rather
 * than a generic placeholder, so the page doesn't visibly "jump" once
 * data arrives.
 */
function OverviewSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading overview">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "var(--space-6)" }}>
        <div>
          <div className="skeleton" style={{ width: 220, height: 28, marginBottom: "var(--space-3)" }} />
          <div className="skeleton" style={{ width: 160, height: 14 }} />
        </div>
        <div className="skeleton" style={{ width: 110, height: 40 }} />
      </div>

      <div style={{ display: "flex", gap: "var(--space-6)", marginBottom: "var(--space-7)" }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card" style={{ flex: 1 }}>
            <div className="skeleton" style={{ width: "60%", height: 14, marginBottom: "var(--space-4)" }} />
            <div className="skeleton" style={{ width: "40%", height: 36 }} />
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-6)", marginBottom: "var(--space-7)" }}>
        <div className="card">
          <div className="skeleton" style={{ width: "50%", height: 20, marginBottom: "var(--space-4)" }} />
          <div className="skeleton" style={{ width: "90%", height: 14 }} />
        </div>
        <div className="card">
          <div className="skeleton" style={{ width: "50%", height: 20, marginBottom: "var(--space-4)" }} />
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ width: `${70 - i * 15}%`, height: 24, marginBottom: "var(--space-3)" }} />
          ))}
        </div>
      </div>

      <div className="skeleton" style={{ width: 100, height: 20, marginBottom: "var(--space-4)" }} />
      <table className="data-table">
        <thead>
          <tr>
            {["Name", "Type", "Rows", "Size", "Last changed", "Projection", "Index", "Quality", "Health"].map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: 4 }).map((_, row) => (
            <tr key={row}>
              {Array.from({ length: 9 }).map((_, col) => (
                <td key={col}>
                  <div className="skeleton" style={{ height: 16, width: col === 0 ? "80%" : "60%" }} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default OverviewSkeleton;
