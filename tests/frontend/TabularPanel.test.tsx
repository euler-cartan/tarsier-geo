import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TabularPanel from "../../frontend/src/screens/TabularPanel";

const ITEM = { schema: "", name: "pipes.csv", kind: "tabular", row_count: 4, row_count_is_estimate: false } as never;
const PREVIEW = {
  columns: [
    { name: "id", type: "int64" },
    { name: "street", type: "object" },
  ],
  rows: [
    { id: 1, street: "Main Rd" },
    { id: 2, street: null },
  ],
  scanned_at: "2026-01-01T00:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init))));
}

describe("TabularPanel", () => {
  it("shows row count, column schema and sample rows (FSD §7)", async () => {
    mockFetch(() => ({ ok: true, json: async () => PREVIEW }));
    render(<TabularPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByText("Main Rd")).toBeDefined();
    expect(screen.getByText("4 rows")).toBeDefined();
    expect(screen.getByText("street · object")).toBeDefined();
    expect(screen.getByText("empty")).toBeDefined();
  });

  it("offers a first load when nothing is cached (empty state)", async () => {
    mockFetch(() => ({ ok: false, json: async () => ({ detail: "Sample rows haven't been loaded for this item yet." }) }));
    render(<TabularPanel connectionId="c1" item={ITEM} />);
    expect(await screen.findByRole("button", { name: "Load sample rows" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("loads rows on demand", async () => {
    let loaded = false;
    mockFetch((_url, init) => {
      if (init?.method === "POST") {
        loaded = true;
        return { ok: true, json: async () => ({ status: "ok" }) };
      }
      return loaded
        ? { ok: true, json: async () => PREVIEW }
        : { ok: false, json: async () => ({ detail: "Sample rows haven't been loaded for this item yet." }) };
    });
    render(<TabularPanel connectionId="c1" item={ITEM} />);
    fireEvent.click(await screen.findByRole("button", { name: "Load sample rows" }));
    expect(await screen.findByText("Main Rd")).toBeDefined();
  });

  it("shows a plain-language error with retry", async () => {
    mockFetch(() => ({ ok: false, json: async () => ({ detail: "Could not read pipes.csv." }) }));
    render(<TabularPanel connectionId="c1" item={ITEM} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Could not read pipes.csv.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });
});
