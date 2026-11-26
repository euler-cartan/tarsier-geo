import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import QualityPanel from "../../frontend/src/screens/QualityPanel";

vi.mock("../../frontend/src/components/MapPreview", () => ({
  default: () => <div>Map preview</div>,
}));

const ITEM = {
  connection_id: "c1",
  schema: "",
  name: "parcels",
  kind: "vector" as const,
  geometry_type: "Polygon",
  srid: 4326,
  row_count: 8,
  row_count_is_estimate: false,
  size_bytes: 100,
  has_index: null,
  last_modified: null,
  is_stale: false,
  is_heavy: false,
  path: "quality.gpkg",
  bbox: [0, 0, 1, 1] as [number, number, number, number],
  raster_width: null,
  raster_height: null,
  raster_band_count: null,
  raster_dtype: null,
  raster_nodata: null,
  scanned_at: "2026-01-01T00:00:00Z",
};

function neverRun(id: string) {
  return { check_id: id, status: "never_run", fail_count: 0, message: null, failing_rows: [], is_sample: false, scanned_at: null };
}

const REPORT = {
  checks: {
    validity: neverRun("validity"),
    overlaps: neverRun("overlaps"),
    slivers: neverRun("slivers"),
    gaps: neverRun("gaps"),
    dangles: neverRun("dangles"),
    completeness: neverRun("completeness"),
    projection: neverRun("projection"),
    boundary: neverRun("boundary"),
    custom_rules: neverRun("custom_rules"),
  },
  rules: [],
  boundary_schema: null,
  boundary_name: null,
  vector_layers: [{ schema: "", name: "city_limit", geometry_type: "Polygon" }],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Quality panel", () => {
  it("shows skipped null rows in the existing result label", async () => {
    const report = { ...REPORT, checks: { ...REPORT.checks, custom_rules: {
      ...neverRun("custom_rules"), status: "good", skipped_count: 3,
      message: "3 rows skipped, value empty", scanned_at: "2026-01-01T00:00:00Z",
    } } };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => report })));
    render(<QualityPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByText("3 rows skipped, value empty")).toBeDefined();
  });

  it("has one action that runs every check and updates results", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).includes("/quality/scan")) {
          return {
            ok: true,
            json: async () => ({
              status: "ok",
              check: {
                check_id: new URL(String(url),"http://test").searchParams.get("check"),
                status: "danger",
                fail_count: 1,
                message: null,
                failing_rows: [{ objectid: 7, centroid_x: 40.5, centroid_y: 40.5 }],
                is_sample: false,
                scanned_at: "2026-01-01T00:00:00Z",
              },
            }),
          };
        }
        if (String(url).includes("/item/quality") && !init?.method) {
          return { ok: true, json: async () => REPORT };
        }
        return { ok: true, json: async () => ({}) };
      })
    );

    render(<QualityPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findAllByText("Not yet run")).not.toHaveLength(0);

    expect(screen.queryByRole("button", {name:"Run now"})).toBeNull();
    await user.click(screen.getByRole("button", {name:"Run checks now"}));

    expect(await screen.findAllByText("1 failed")).not.toHaveLength(0);
    expect(await screen.findByText("Checks finished. Review the results and any errors below.")).toBeDefined();
    expect(screen.queryByText("Not yet run")).toBeNull();
  });

  it("lists failing features and can show them on the map", async () => {
    const user = userEvent.setup();
    const withFail = {
      ...REPORT,
      checks: {
        ...REPORT.checks,
        validity: {
          check_id: "validity",
          status: "danger",
          fail_count: 1,
          message: null,
          failing_rows: [{ objectid: 7, centroid_x: 40.5, centroid_y: 40.5 }],
          is_sample: false,
          scanned_at: "2026-01-01T00:00:00Z",
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => withFail }))
    );
    render(<QualityPanel connectionId="c1" item={ITEM} />);
    await user.click(await screen.findByRole("button", { name: /Geometry validity/ }));
    expect(await screen.findByText("7")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Show on map" }));
    expect(screen.getByText("Map preview")).toBeDefined();
  });
});
