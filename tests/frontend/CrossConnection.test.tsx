/** TRS-118 — the flowchart can compare with other connections and says what it found. */
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Flowchart from "../../frontend/src/screens/Flowchart";

// jsdom has no canvas, which Cytoscape needs; the graph drawing itself is not under test here.
vi.mock("cytoscape", () => ({
  default: () => ({ on: () => {}, destroy: () => {}, nodes: () => ({ forEach: () => {} }), edges: () => ({ removeClass: () => {} }) }),
}));

afterEach(() => vi.unstubAllGlobals());

const GRAPH = {
  nodes: [{ schema: "", name: "parcels.csv", kind: "tabular", columns: ["parcel_id"] }],
  external_nodes: [{ schema: "", name: "taxes.csv", kind: "tabular", columns: [], connection_id: "c2", connection_name: "Source B" }],
  links: [{
    id: "l1", source_schema: "", source_name: "parcels.csv", source_column: "parcel_id", target_schema: "", target_name: "taxes.csv",
    target_column: "parcel_id", kind: "guessed", status: "guessed", sample_based: false,
    source_connection_id: "c1", target_connection_id: "c2",
  }],
};

function renderFlowchart(scanResult: object) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      return Promise.resolve({ ok: true, json: async () => (String(url).includes("/cross/scan") ? scanResult : GRAPH) });
    })
  );
  render(
    <MemoryRouter initialEntries={["/connections/c1/flowchart"]}>
      <Routes>
        <Route path="/connections/:connectionId/flowchart" element={<Flowchart />} />
      </Routes>
    </MemoryRouter>
  );
  return calls;
}

describe("Flowchart cross-connection scan", () => {
  it("runs the comparison and reports the number of guesses", async () => {
    const calls = renderFlowchart({ guesses: 2, skipped_connections: [] });
    fireEvent.click(await screen.findByRole("button", { name: "Compare with other connections" }));
    expect(await screen.findByText(/2 possible connections found/)).toBeDefined();
    expect(calls).toContain("POST /api/flowchart/cross/scan");
  });

  it("names any connection it could not read instead of failing", async () => {
    renderFlowchart({ guesses: 0, skipped_connections: ["Old server"] });
    fireEvent.click(await screen.findByRole("button", { name: "Compare with other connections" }));
    expect(await screen.findByText(/0 possible connections found.*Could not read: Old server/)).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("explains the dashed-box convention in the legend", async () => {
    renderFlowchart({ guesses: 0, skipped_connections: [] });
    expect(await screen.findByText("Dashed box: item in another connection")).toBeDefined();
  });
});
