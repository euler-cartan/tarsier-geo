/** TRS-116 — the item detail Connections tab (FSD §7). */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ItemDetail from "../../frontend/src/screens/ItemDetail";

vi.mock("../../frontend/src/components/MapPreview", () => ({ default: () => <div>Map preview</div> }));

const ITEM = {
  connection_id: "c1", schema: "public", name: "parcels", kind: "vector", geometry_type: "Polygon", srid: 4326,
  row_count: 1, row_count_is_estimate: false, size_bytes: 1, has_index: null, last_modified: null, is_stale: false,
  is_heavy: false, path: null, bbox: null, raster_width: null, raster_height: null, raster_band_count: null,
  raster_dtype: null, raster_nodata: null, scanned_at: "2026-01-01T00:00:00Z",
};
const link = (over: object) => ({
  id: "l", source_schema: "public", source_name: "parcels", source_column: "owner_id", target_schema: "public",
  target_name: "owners", target_column: "id", kind: "official", status: "confirmed", sample_based: false, ...over,
});

afterEach(() => vi.unstubAllGlobals());

function open(links: object[], flowchartOk = true, neighbors: object[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        String(url).includes("/api/graph/neighbors")
          ? { ok: true, json: async () => ({ items: neighbors }) }
          : String(url).includes("/flowchart")
          ? flowchartOk
            ? { ok: true, json: async () => ({ nodes: [], links }) }
            : { ok: false, json: async () => ({ detail: "Could not load the connection flowchart." }) }
          : { ok: true, json: async () => ITEM }
      )
    )
  );
  render(
    <MemoryRouter initialEntries={["/connections/c1/items?schema=public&name=parcels"]}>
      <Routes>
        <Route path="/connections/:connectionId/items" element={<ItemDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Connections tab", () => {
  it("lists only this item's links, from either side, with the connected item as a link", async () => {
    open([
      link({ id: "a" }),
      link({ id: "b", kind: "guessed", status: "guessed", source_name: "zones", source_column: "zone", target_name: "parcels", target_column: "zone_code" }),
      link({ id: "c", source_name: "roads", target_name: "bridges" }),
    ]);
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    expect(await screen.findByRole("link", { name: "owners" })).toBeDefined();
    expect(screen.getByRole("link", { name: "zones" })).toBeDefined();
    expect(screen.queryByText("roads")).toBeNull();
    expect(screen.getByText("Official")).toBeDefined();
    expect(screen.getByText("Guessed ?")).toBeDefined();
    expect(screen.getByRole("link", { name: "owners" }).getAttribute("href")).toContain("name=owners");
  });

  it("shows an empty state with a way to the flowchart", async () => {
    open([]);
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    expect(await screen.findByText("No connections found for this item")).toBeDefined();
    expect(screen.getByRole("link", { name: "Open the full flowchart" })).toBeDefined();
  });

  it("shows an error with Retry", async () => {
    open([], false);
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });

  it("sends cross-connection links to the other connection's item and labels them", async () => {
    open([link({ id: "x", target_connection_id: "c2", target_name: "taxes.csv", target_column: "parcel_id", source_connection_id: "c1", kind: "guessed", status: "guessed" })]);
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    const anchor = await screen.findByRole("link", { name: "taxes.csv" });
    expect(anchor.getAttribute("href")).toContain("/connections/c2/items");
    expect(screen.getByText(/in another connection/)).toBeDefined();
  });

  it("does not mistake a same-named item in another connection for this one", async () => {
    open([link({ id: "y", source_connection_id: "c9", source_name: "parcels", target_connection_id: "c2", target_name: "other" })]);
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    expect(await screen.findByText("No connections found for this item")).toBeDefined();
  });

  it("links to the Relationship Graph for this item and no longer shows the interim related list", async () => {
    open([link({})]);
    const anchor = await screen.findByRole("link", { name: "View in Relationship Graph" });
    fireEvent.click(await screen.findByRole("button", { name: "Connections" }));
    expect(anchor.getAttribute("href")).toBe("/connections/c1/graph?schema=public&name=parcels");
    expect(screen.queryByText("Also related, through other items")).toBeNull();
  });
});
