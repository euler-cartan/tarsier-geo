import { Ico } from "../components/Icon";
import { ReactNode, useEffect, useState } from "react";
import { CachedItem, getItemRaster, RasterBand, RasterDetail, scanItemRaster } from "../api";
import RasterHistogram from "../components/RasterHistogram";
import { formatDate } from "../format";

function Field({ label, children }: { label: string; children: ReactNode | null | undefined }) {
  const empty = children === null || children === undefined || children === "";
  return (
    <>
      <dt className="t-caption">{label}</dt>
      <dd>{empty ? <span style={{ color: "var(--ink-faint)" }}>Not available</span> : children}</dd>
    </>
  );
}

function num(value: number | null, digits = 4): string | null {
  return value === null ? null : Number(value.toPrecision(digits)).toLocaleString();
}

/** PRD §8 / FSD §7 / DVS §10  -  raster fields, per-band numbers, and histogram on the raster Overview tab. */
function RasterPanel({ connectionId, item }: { connectionId: string; item: CachedItem }) {
  const [detail, setDetail] = useState<RasterDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [bandIndex, setBandIndex] = useState(1);
  const [logScale, setLogScale] = useState(false);
  const [justFull, setJustFull] = useState(false);

  function load() {
    setLoading(true);
    return getItemRaster(connectionId, item.schema, item.name)
      .then((body) => {
        setDetail(body);
        setMissing(false);
        setError(null);
      })
      .catch((err) => {
        setDetail(null);
        if (String(err.message).includes("hasn't been read")) setMissing(true);
        else setError(err.message);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, [connectionId, item.schema, item.name]);

  async function run(full: boolean) {
    setRunning(true);
    setError(null);
    try {
      await scanItemRaster(connectionId, item.schema, item.name, full);
      await load();
      if (full) {
        setJustFull(true);
        window.setTimeout(() => setJustFull(false), 4000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read this raster.");
    } finally {
      setRunning(false);
    }
  }

  const band: RasterBand | undefined = detail?.bands.find((b) => b.index === bandIndex) ?? detail?.bands[0];

  return (
    <div className="card" style={{ marginTop: "var(--space-6)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <h2 className="t-heading-lg" style={{ margin: 0 }}>Raster detail</h2>
        {detail?.is_sample && (
          <span className="t-caption" style={{ background: "var(--hairline)", borderRadius: 999, padding: "2px 10px" }}>
            {detail.sample_note ?? "Based on a sample"}
          </span>
        )}
        {justFull && (
          <span className="t-caption" role="status">
            Now showing full data
          </span>
        )}
        <button type="button" className="button-secondary-outline" onClick={() => run(false)} disabled={running}><Ico t={detail ? "Refresh" : "Read raster now"} /></button>
        {detail?.is_sample && (
          <button type="button" className="button-secondary-outline" onClick={() => run(true)} disabled={running}><Ico t="Run full check" /></button>
        )}
      </div>

      {loading && <div className="skeleton" style={{ height: 200, marginTop: "var(--space-4)" }} aria-label="Loading raster detail" />}

      {!loading && missing && (
        <p className="t-caption" style={{ marginTop: "var(--space-4)" }}>
          Pixel size, band statistics and histograms haven't been read yet. Use "Read raster now" to compute them.
        </p>
      )}

      {error && (
        <p style={{ color: "var(--status-danger)" }} role="alert">
          {error}{" "}
          <button type="button" className="button-secondary-outline" onClick={() => load()}><Ico t="Retry" /></button>
        </p>
      )}

      {detail && (
        <>
          <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--space-3) var(--space-5)", marginTop: "var(--space-4)" }}>
            <Field label="Pixel size">
              {detail.pixel_size_x !== null && detail.pixel_size_y !== null
                ? `${num(detail.pixel_size_x)} × ${num(detail.pixel_size_y)}${detail.pixel_size_unit ? ` ${detail.pixel_size_unit}` : ""}`
                : null}
            </Field>
            <Field label="Dimensions">
              {detail.width && detail.height ? `${detail.width.toLocaleString()} × ${detail.height.toLocaleString()} px` : null}
            </Field>
            <Field label="Bands">
              {detail.band_count !== null ? `${detail.band_count} (${detail.bands.map((b) => b.name).join(", ")})` : null}
            </Field>
            <Field label="Projection">{detail.crs}</Field>
            <Field label="Footprint">{detail.footprint ? detail.footprint.map((v) => Number(v.toFixed(5))).join(", ") : null}</Field>
            <Field label="Acquisition date">{detail.acquisition_date}</Field>
            <Field label="Sensor">{detail.sensor}</Field>
            <Field label="Cloud cover">{detail.cloud_cover !== null ? `${detail.cloud_cover}%` : null}</Field>
            <Field label="Data type (bit depth)">{detail.dtype}</Field>
            <Field label="Nodata value">{detail.nodata !== null ? String(detail.nodata) : null}</Field>
            <Field label="Overviews present">{detail.has_overviews === null ? null : detail.has_overviews ? "Yes" : "No"}</Field>
            <Field label="Last read">{formatDate(detail.scanned_at)}</Field>
          </dl>

          {band && (
            <>
              <h3 className="t-heading-lg" style={{ marginBottom: "var(--space-3)" }}>Per-band statistics</h3>
              <div role="tablist" aria-label="Band" style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
                {detail.bands.map((b) => (
                  <button
                    key={b.index}
                    type="button"
                    role="tab"
                    aria-selected={b.index === band.index}
                    className={b.index === band.index ? "button-primary-dark" : "button-secondary-outline"}
                    onClick={() => setBandIndex(b.index)}
                  >
                    {b.name}
                  </button>
                ))}
              </div>
              <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "var(--space-3) var(--space-5)" }}>
                <Field label="Minimum">{num(band.minimum)}</Field>
                <Field label="Maximum">{num(band.maximum)}</Field>
                <Field label="Average">{num(band.average)}</Field>
                <Field label="Spread (std. deviation)">{num(band.spread)}</Field>
                <Field label="Nodata (empty)">{band.nodata_percent !== null ? `${band.nodata_percent}% of pixels` : null}</Field>
              </dl>
              <label className="t-caption" style={{ display: "inline-flex", gap: "var(--space-2)", alignItems: "center", minHeight: 40 }}>
                <input type="checkbox" checked={logScale} onChange={(e) => setLogScale(e.target.checked)} />
                Log scale
              </label>
              <RasterHistogram band={band} logScale={logScale} />
            </>
          )}
        </>
      )}
    </div>
  );
}

export default RasterPanel;
