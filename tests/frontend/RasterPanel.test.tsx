import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RasterPanel from "../../frontend/src/screens/RasterPanel";

const ITEM = { schema: "", name: "dem.tif", kind: "raster" } as never;

const bin = (start: number, end: number, count: number) => ({ start, end, count });
const DETAIL = {
  width: 400,
  height: 300,
  band_count: 2,
  pixel_size_x: 30,
  pixel_size_y: 30,
  pixel_size_unit: "metre",
  crs: "EPSG:32633",
  srid: 32633,
  footprint: [500000, 3991000, 512000, 4000000],
  acquisition_date: null,
  sensor: null,
  cloud_cover: null,
  dtype: "float32",
  nodata: -9999,
  has_overviews: false,
  is_sample: false,
  sample_note: null,
  scanned_at: "2026-01-01T00:00:00Z",
  bands: [
    {
      index: 1, name: "Elevation", dtype: "float32", nodata: -9999, minimum: 5, maximum: 16, average: 10.5,
      spread: 3.4, nodata_percent: 25, valid_pixel_count: 12, histogram: [bin(5, 10, 6), bin(10, 16, 6)],
    },
    {
      index: 2, name: "Slope", dtype: "float32", nodata: -9999, minimum: 0, maximum: 2, average: 1,
      spread: 0.5, nodata_percent: 0, valid_pixel_count: 16, histogram: [bin(0, 1, 8), bin(1, 2, 8)],
    },
  ],
};

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)))
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RasterPanel", () => {
  it("shows PRD §8 fields and 'Not available' for absent metadata (TRS-079, TRS-083)", async () => {
    mockFetch(() => ({ ok: true, json: async () => DETAIL }));
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByText("30 × 30 metre")).toBeDefined();
    expect(screen.getByText("400 × 300 px")).toBeDefined();
    expect(screen.getByText("EPSG:32633")).toBeDefined();
    // acquisition date, sensor and cloud cover are all absent -> graceful text, no error
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows per-band stats and nodata %, and the band selector switches bands (TRS-080/081/082)", async () => {
    mockFetch(() => ({ ok: true, json: async () => DETAIL }));
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByText("25% of pixels")).toBeDefined();
    expect(screen.getByText("10.5")).toBeDefined();
    fireEvent.click(screen.getByRole("tab", { name: "Slope" }));
    expect(screen.getByText("0% of pixels")).toBeDefined();
    expect(screen.getByRole("tab", { name: "Slope" }).getAttribute("aria-selected")).toBe("true");
  });

  it("toggles log scale", async () => {
    mockFetch(() => ({ ok: true, json: async () => DETAIL }));
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    const box = (await screen.findByLabelText("Log scale")) as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    expect(box.checked).toBe(true);
  });

  it("offers a first read when nothing is cached yet (empty state)", async () => {
    mockFetch((url, init) =>
      init?.method === "POST"
        ? { ok: true, json: async () => ({ status: "ok" }) }
        : { ok: false, json: async () => ({ detail: "Raster detail hasn't been read for this item yet." }) }
    );
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByRole("button", { name: "Read raster now" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a plain-language error with retry", async () => {
    mockFetch(() => ({ ok: false, json: async () => ({ detail: "Could not read dem.tif." }) }));
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Could not read dem.tif.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });

  it("labels a sampled result, and Run full check removes the label (DVS §12)", async () => {
    let full = false;
    mockFetch((url, init) => {
      if (init?.method === "POST") {
        full = url.includes("full=true");
        return { ok: true, json: async () => ({ status: "ok" }) };
      }
      return {
        ok: true,
        json: async () => ({ ...DETAIL, is_sample: !full, sample_note: full ? null : "Based on a sample (about 4,000,000 pixels per band)" }),
      };
    });
    render(<RasterPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByText(/Based on a sample/)).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Run full check" }));
    await waitFor(() => expect(screen.queryByText(/Based on a sample/)).toBeNull());
    expect(await screen.findByText("Now showing full data")).toBeDefined();
  });
});
