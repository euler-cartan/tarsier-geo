import { PolarAngleAxis, RadialBar, RadialBarChart } from "recharts";
import type { HealthComponents } from "../api";

/** DVS §4 - weighted health score ring and component breakdown. */
function HealthRing({ score, components, isSample = false, componentsAreAverages = false, coverageCount, totalLayers, size = "large" }: { isSample?: boolean; score: number | null; components?: HealthComponents; componentsAreAverages?: boolean; coverageCount?: number; totalLayers?: number; size?: "large" | "small" }) {
  const diameter = size === "large" ? 96 : 28;
  const coverageNote = coverageCount !== undefined && totalLayers !== undefined && coverageCount < totalLayers
    ? `${score}, based on ${coverageCount} of ${totalLayers} items`
    : undefined;

  const breakdown = components
    ? `${componentsAreAverages ? "Average across layers  -  " : ""}Quality: ${components.quality ?? "unavailable"}; Freshness: ${components.freshness ?? "unavailable"}; Completeness: ${components.completeness ?? "unavailable"}`
    : undefined;

  if (score === null) {
    if (size === "small") {
      return <span title="No health components are available" className="t-caption" style={{ color: "var(--ink-faint)" }}> - </span>;
    }
    return (
      <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "var(--space-2)" }}>
        <div
          style={{
            width: diameter,
            height: diameter,
            borderRadius: "50%",
            border: `${size === "large" ? 8 : 3}px solid var(--hairline)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-faint)",
          }}
          className={size === "large" ? "t-stat-xl" : "t-caption"}
        >
          –
        </div>
        {size === "large" && (
          <span className="t-micro" style={{ color: "var(--ink-faint)" }}>
            No applicable health results are available.
          </span>
        )}
      </div>
    );
  }

  const color = isSample ? "var(--ink-faint)" : score >= 80 ? "var(--status-good)" : score >= 50 ? "var(--status-warning)" : "var(--status-danger)";
  const data = [{ value: score, fill: color }];

  if (size === "small") {
    return (
      <span title={breakdown} aria-label={`Health score ${score}${coverageNote ? `; ${coverageNote}` : ""}${isSample ? " (sample-based; not a full check)" : ""}. ${breakdown ?? ""}`} style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}>
        <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
        <span className="t-micro">{coverageNote ?? score}{isSample && " (sample-based)"}</span>
      </span>
    );
  }

  return (
    <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "var(--space-1)" }}>
      <div
        title={breakdown}
        aria-label={`Health score ${score}${coverageNote ? `; ${coverageNote}` : ""}${isSample ? " (sample-based; not a full check)" : ""}. ${breakdown ?? ""}`}
        style={{ width: diameter, height: diameter, position: "relative" }}
      >
        <RadialBarChart width={diameter} height={diameter} cx="50%" cy="50%" innerRadius="70%" outerRadius="100%" barSize={8} data={data} startAngle={90} endAngle={-270}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar dataKey="value" cornerRadius={99} animationDuration={300} background={{ fill: "var(--hairline)" }} />
        </RadialBarChart>
        <span className="health-score" style={{ fontSize: 30, lineHeight: 1, fontVariantNumeric: "tabular-nums", position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          {score}
        </span>
      </div>
      {isSample && <span className="t-micro">Sample-based; not a full check</span>}
      {coverageNote && <span className="t-micro">{coverageNote}</span>}
      {componentsAreAverages && <span className="t-micro" style={{ color: "var(--ink-faint)" }}>Component averages across layers</span>}
    </div>
  );
}

export default HealthRing;
