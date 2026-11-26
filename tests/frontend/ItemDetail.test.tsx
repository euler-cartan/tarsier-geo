import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ItemDetail from "../../frontend/src/screens/ItemDetail";

vi.mock("../../frontend/src/components/MapPreview", () => ({
  default: () => <div>Map preview</div>,
}));

const RASTER = {
  connection_id: "c1",
  schema: "",
  name: "sample_elevation.tif",
  kind: "raster",
  geometry_type: null,
  srid: 4326,
  row_count: null,
  row_count_is_estimate: false,
  size_bytes: 100,
  has_index: null,
  last_modified: null,
  is_stale: false,
  is_heavy: false,
  path: "sample_elevation.tif",
  bbox: [0, 0, 1, 1],
  raster_width: 10,
  raster_height: 10,
  raster_band_count: 1,
  raster_dtype: "float32",
  raster_nodata: -9999,
  scanned_at: "2026-01-01T00:00:00Z",
};

const TABULAR = { ...RASTER, name: "pipes.csv", kind: "tabular", raster_width: null };
const VECTOR = { ...RASTER, name: "roads", kind: "vector", geometry_type: "LineString", raster_width: null };

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderItem(item: typeof RASTER) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        String(url).includes("/item/raster") || String(url).includes("/item/preview")
          ? { ok: false, json: async () => ({ detail: "Raster detail hasn't been read for this item yet." }) }
          : { ok: true, json: async () => item }
      )
    )
  );
  return render(
    <MemoryRouter initialEntries={[`/connections/c1/items?schema=&name=${item.name}`]}>
      <Routes>
        <Route path="/connections/:connectionId/items" element={<ItemDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Item detail tabs", () => {
  it("hides the Statistics tab for raster items", async () => {
    renderItem(RASTER);
    expect(await screen.findByRole("heading", { name: "sample_elevation.tif" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Statistics" })).toBeNull();
  });

  it("shows the Statistics tab for vector items", async () => {
    renderItem(VECTOR);
    expect(await screen.findByRole("heading", { name: "roads" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Statistics" })).toBeDefined();
  });

  it("hides the Quality tab for raster items", async () => {
    renderItem(RASTER);
    expect(await screen.findByRole("heading", { name: "sample_elevation.tif" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Quality" })).toBeNull();
  });

  it("shows the Quality tab for vector items", async () => {
    renderItem(VECTOR);
    expect(await screen.findByRole("heading", { name: "roads" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Quality" })).toBeDefined();
  });

  it("hides the History tab for raster items", async () => {
    renderItem(RASTER);
    expect(await screen.findByRole("heading", { name: "sample_elevation.tif" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "History" })).toBeNull();
  });

  it("shows Statistics, Quality and History tabs but no map for tabular items (TRS-085/086)", async () => {
    renderItem(TABULAR);
    expect(await screen.findByRole("heading", { name: "pipes.csv" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Statistics" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Quality" })).toBeDefined();
    expect(screen.queryByText("Map preview")).toBeNull();
    expect(await screen.findByRole("button", { name: "Load sample rows" })).toBeDefined();
  });
});
