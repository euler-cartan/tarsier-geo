import { Bar, BarChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";
import { RasterBand } from "../api";
import { palette } from "../design";

/** DVS §10  -  bar histogram of one band; min/max/mean as dashed reference lines; log-scale toggle. */
function RasterHistogram({ band, logScale }: { band: RasterBand; logScale: boolean }) {
  if (band.histogram.length === 0) {
    return <p className="t-caption">This band has no valid pixels to chart.</p>;
  }
  const data = band.histogram.map((b) => ({
    mid: (b.start + b.end) / 2,
    count: b.count,
    label: `${b.start.toPrecision(4)}–${b.end.toPrecision(4)}`,
  }));
  return (
    <BarChart width={560} height={200} data={data} margin={{ left: 8, right: 8 }} aria-label={`Histogram of ${band.name}`}>
      <XAxis dataKey="mid" type="number" domain={["dataMin", "dataMax"]} tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      {logScale ? (
        <YAxis scale="log" domain={[1, "auto"]} allowDataOverflow tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      ) : (
        <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: "var(--ink-mute)" }} />
      )}
      <Tooltip labelFormatter={(_, payload) => payload?.[0]?.payload?.label ?? ""} />
      <Bar dataKey="count" fill={palette.primary} />
      {band.minimum != null && <ReferenceLine x={band.minimum} stroke={palette.primary} strokeDasharray="4 4" />}
      {band.maximum != null && <ReferenceLine x={band.maximum} stroke={palette.primary} strokeDasharray="4 4" />}
      {band.average != null && <ReferenceLine x={band.average} stroke={palette.primary} strokeDasharray="4 4" />}
    </BarChart>
  );
}

export default RasterHistogram;
