import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import StatisticsPanel from "../../frontend/src/screens/StatisticsPanel";

vi.mock("../../frontend/src/components/MapPreview", () => ({
  default: () => <div>Map preview</div>,
}));

const ITEM = {
  connection_id: "c1",
  schema: "",
  name: "sample_inventory.csv",
  kind: "tabular" as const,
  geometry_type: null,
  srid: null,
  row_count: 6,
  row_count_is_estimate: false,
  size_bytes: 100,
  has_index: null,
  last_modified: null,
  is_stale: false,
  is_heavy: false,
  path: "sample_inventory.csv",
  bbox: null,
  raster_width: null,
  raster_height: null,
  raster_band_count: null,
  raster_dtype: null,
  raster_nodata: null,
  scanned_at: "2026-01-01T00:00:00Z",
};

const STATS = {
  sampled_row_count: 6,
  is_sample: false,
  columns: [
    {
      name: "diameter_mm",
      is_numeric: true,
      minimum: 100,
      maximum: 250,
      average: 170,
      empty_count: 1,
      unique_count: 4,
      top_values: [["150", 2]],
      messy_groups: [],
      out_of_range_count: 0,
      histogram: [{ start: 100, end: 150, count: 2 }],
    },
  ],
  duplicate_row_count: 1,
  null_geometry_count: null,
  spatial_outlier_count: null,
  messy_category_rows: [],
  out_of_range_rows: [],
  duplicate_rows: [
    { id: 1, material: "PVC" },
    { id: 2, material: "PVC" },
  ],
  map_outlier_rows: [],
  null_geometry_rows: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Statistics tab", () => {
  it("clicking Duplicates lists the matching rows (TRS-028)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (String(url).includes("/settings/ai")) {
          return { ok: true, json: async () => ({ configured: false, privacy_warning: null }) };
        }
        if (String(url).includes("/item/stats")) {
          return { ok: true, json: async () => STATS };
        }
        return { ok: false, json: async () => ({ detail: "no" }) };
      })
    );
    render(
      <MemoryRouter>
        <StatisticsPanel connectionId="c1" item={ITEM} />
      </MemoryRouter>
    );
    expect(await screen.findByText("diameter_mm")).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: /Duplicates: 2/ }));
    expect(await screen.findByText("Matching rows")).toBeDefined();
    expect(screen.getAllByText("PVC").length).toBe(2);
  });
});
