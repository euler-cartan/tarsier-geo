/** TRS-102 (DVS §12) — sampled results are labelled, offer a full run, and say so when the full data replaces them. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import QualityPanel from "../../frontend/src/screens/QualityPanel";
import StatisticsPanel from "../../frontend/src/screens/StatisticsPanel";
import { formatRowCount } from "../../frontend/src/format";

vi.mock("../../frontend/src/components/MapPreview", () => ({ default: () => <div>Map preview</div> }));

const ITEM = {
  connection_id: "c1", schema: "", name: "big.csv", kind: "tabular", geometry_type: null, srid: null,
  row_count: 1500, row_count_is_estimate: false, size_bytes: 1, has_index: null, last_modified: null,
  is_stale: false, is_heavy: false, path: "big.csv", bbox: null, raster_width: null, raster_height: null,
  raster_band_count: null, raster_dtype: null, raster_nodata: null, scanned_at: "2026-01-01T00:00:00Z",
} as never;

afterEach(() => vi.unstubAllGlobals());

function statsBody(isSample: boolean) {
  return {
    sampled_row_count: isSample ? 1000 : 1500, is_sample: isSample,
    columns: [], duplicate_row_count: 0, null_geometry_count: null, spatial_outlier_count: null,
    messy_category_rows: [], out_of_range_rows: [], duplicate_rows: [], map_outlier_rows: [], null_geometry_rows: [],
  };
}

describe("Statistics sample label", () => {
  it("renders the bounded count sentinel as more than 20,000", () => {
    expect(formatRowCount(20_001, false, true)).toBe("more than 20,000");
  });

  it("shows the sample tag and Run full check, then confirms full data and drops the tag", async () => {
    let full = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          full = String(url).includes("full=true");
          return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
        }
        return Promise.resolve({ ok: true, json: async () => statsBody(!full) });
      })
    );
    render(
      <MemoryRouter>
        <StatisticsPanel connectionId="c1" item={ITEM} />
      </MemoryRouter>
    );
    expect(await screen.findByText(/Based on a sample \(1,000 rows\)/)).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Run full check" }));
    await waitFor(() => expect(screen.queryByText(/Based on a sample/)).toBeNull());
    expect(await screen.findByText("Now showing full data")).toBeDefined();
  });

  it("replaces full statistics with the release notice above 20,000 rows", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => statsBody(true) })));
    render(<MemoryRouter><StatisticsPanel connectionId="c1" item={{ ...ITEM, row_count: 20_001 } as never} /></MemoryRouter>);
    expect(await screen.findByText("Full statistics are not available for tables this large in this release. Sample statistics are shown and labelled.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Run full check" })).toBeNull();
  });

  it("shows the large-table notice before its first sample is run", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({ detail: "Statistics haven't been run for this item yet." }) })));
    render(<MemoryRouter><StatisticsPanel connectionId="c1" item={{ ...ITEM, row_count: 20_001 } as never} /></MemoryRouter>);
    expect(await screen.findByText("Full statistics are not available for tables this large in this release. No sample statistics are available yet.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Run now" })).toBeDefined();
  });

  it("shows the empty-table state and does not offer a full check", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({ detail: "Statistics haven't been run for this item yet." }) })));
    render(<MemoryRouter><StatisticsPanel connectionId="c1" item={{ ...ITEM, row_count: 0 } as never} /></MemoryRouter>);
    expect(await screen.findByText("This table has no rows")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Run full check" })).toBeNull();
  });

  it("uses an accurate message when the row count is unknown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({ detail: "Statistics haven't been run for this item yet." }) })));
    render(<MemoryRouter><StatisticsPanel connectionId="c1" item={{ ...ITEM, row_count: null } as never} /></MemoryRouter>);
    expect(await screen.findByText("Full statistics were not run because the table size could not be determined.")).toBeDefined();
    expect(screen.queryByText(/sample statistics are shown/i)).toBeNull();
  });

  it("keeps the sample visible while a permitted full statistics run is pending", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return new Promise(() => {});
      return Promise.resolve({ ok: true, json: async () => statsBody(true) });
    }));
    render(<MemoryRouter><StatisticsPanel connectionId="c1" item={ITEM} /></MemoryRouter>);
    expect(await screen.findByText(/Based on a sample \(1,000 rows\)/)).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Run full check" }));
    expect(screen.getByText("Checking all rows; the current sample remains visible while this runs.")).toBeDefined();
    expect(screen.getByText(/Based on a sample \(1,000 rows\)/)).toBeDefined();
  });
});

describe("Quality sample label", () => {
  const checks = (isSample: boolean) => ({
    checks: {
      completeness: { check_id: "completeness", status: "never_run", fail_count: 0, message: null, failing_rows: [], is_sample: false, scanned_at: null },
      custom_rules: {
        check_id: "custom_rules", status: isSample ? "good" : "danger", fail_count: isSample ? 0 : 300, message: null,
        failing_rows: [], is_sample: isSample, scanned_at: "2026-01-01T00:00:00Z",
      },
    },
    rules: [], boundary_schema: null, boundary_name: null, vector_layers: [],
  });

  it("labels a sampled check, offers a full run, and replaces the result", async () => {
    let full = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          full = String(url).includes("full=true");
          return Promise.resolve({ ok: true, json: async () => ({ status: "ok", check: String(url).includes("check=custom_rules") ? checks(!full).checks.custom_rules : {...checks(false).checks.completeness,status:"good"} }) });
        }
        return Promise.resolve({ ok: true, json: async () => checks(true) });
      })
    );
    render(
      <MemoryRouter>
        <QualityPanel connectionId="c1" item={ITEM} />
      </MemoryRouter>
    );
    expect(await screen.findByText("Based on a sample")).toBeDefined();
    expect(screen.getByText("none found in sample, not a full check")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Run checks now" }));
    await waitFor(() => expect(screen.queryByText("Based on a sample")).toBeNull());
    expect(await screen.findByText("Checks finished. Review the results and any errors below.")).toBeDefined();
    expect(screen.getByText("300 failed")).toBeDefined();
  });
});
