import { Bar, BarChart, Cell, Tooltip, XAxis, YAxis } from "recharts";
import { ProjectionGroup } from "../api";

/** DVS §11  -  Projection overview: horizontal grouped bar, one per CRS
 * found. Majority CRS in `--primary`; any minority/mismatched CRS in
 * `--status-warning`. Clicking a bar filters the layer table (handled by
 * the caller via `onSelect`). */
function ProjectionChart({
  projections,
  onSelect,
}: {
  projections: ProjectionGroup[];
  onSelect?: (srid: number | null) => void;
}) {
  if (projections.length === 0) {
    return <p className="t-caption">No projection information yet  -  run a check to populate this.</p>;
  }

  const data = projections.map((p) => ({
    label: p.srid ? `EPSG:${p.srid}` : "Unknown",
    count: p.layer_count,
    isMajority: p.is_majority,
    srid: p.srid,
  }));

  return (
    <BarChart
      width={420}
      height={Math.max(60, data.length * 36)}
      data={data}
      layout="vertical"
      margin={{ left: 16 }}
      onClick={(state) => {
        const index = state?.activeTooltipIndex;
        if (onSelect && typeof index === "number" && data[index]) onSelect(data[index].srid);
      }}
    >
      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      <YAxis type="category" dataKey="label" tick={{ fontSize: 12, fill: "var(--ink-mute)" }} width={90} />
      <Tooltip formatter={(value) => [`${value} layer${value === 1 ? "" : "s"}`, "Count"]} />
      <Bar dataKey="count" radius={[0, 4, 4, 0]} cursor="pointer">
        {data.map((entry, index) => (
          <Cell key={index} fill={entry.isMajority ? "var(--primary)" : "var(--status-warning)"} />
        ))}
      </Bar>
    </BarChart>
  );
}

export default ProjectionChart;
