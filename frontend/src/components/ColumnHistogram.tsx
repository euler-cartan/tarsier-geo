import { Bar, BarChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { ColumnStats } from "../api";
import { palette } from "../design";

/** DVS §7  -  always 15 bins; min/max/average as dashed status-info lines. */
function ColumnHistogram({ column }: { column: ColumnStats }) {
  const bins = column.histogram ?? [];
  if (!column.is_numeric) {
    const freq = column.top_values.map(([value, count]) => ({ label: value, count }));
    if (freq.length === 0) {
      return <p className="t-caption">No values.</p>;
    }
    return (
      <BarChart width={480} height={160} data={freq} margin={{ left: 8, right: 8 }}>
        <XAxis dataKey="label" tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
        <Tooltip />
        <Bar dataKey="count" fill={palette.primary} />
      </BarChart>
    );
  }
  if (bins.length === 0) {
    return <p className="t-caption">No values.</p>;
  }
  const data = bins.map((b) => ({
    mid: (b.start + b.end) / 2,
    count: b.count,
    label: `${b.start.toPrecision(4)}–${b.end.toPrecision(4)}`,
  }));
  return (
    <BarChart width={480} height={180} data={data} margin={{ left: 8, right: 8 }}>
      <XAxis dataKey="mid" type="number" tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      <Tooltip labelFormatter={(_, payload) => payload?.[0]?.payload?.label ?? ""} />
      <Bar dataKey="count" fill={palette.primary} />
      {column.minimum != null && (
        <ReferenceLine x={Number(column.minimum)} stroke={palette.primary} strokeDasharray="4 4" />
      )}
      {column.maximum != null && (
        <ReferenceLine x={Number(column.maximum)} stroke={palette.primary} strokeDasharray="4 4" />
      )}
      {column.average != null && (
        <ReferenceLine x={column.average} stroke={palette.primary} strokeDasharray="4 4" />
      )}
    </BarChart>
  );
}

export default ColumnHistogram;
