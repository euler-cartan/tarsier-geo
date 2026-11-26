/** TRS-119 - the Relationship Graph screen (FSD 12.1). */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import RelationshipGraph from "../../frontend/src/screens/RelationshipGraph";

// jsdom has no canvas; capture what would be drawn and the tap handler instead.
type Element = { data: Record<string, unknown>; classes?: string };
const drawn: { elements: Element[] }[] = [];
let tapNode: ((event: unknown) => void) | null = null;
vi.mock("cytoscape", () => ({
  default: (options: { elements: Element[] }) => {
    drawn.push({ elements: options.elements });
    return {
      on: (_event: string, selector: string, handler: (event: unknown) => void) => {
        if (selector === "node") tapNode = handler;
      },
      destroy: () => {},
    };
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  drawn.length = 0;
  tapNode = null;
});

const item = (cid: string, name: string, cname: string) => ({ key: `${cid}||${name}`, connection_id: cid, schema: "", name, kind: "tabular", connection_name: cname });
const A = item("c1", "parcels.csv", "Source A");
const B = item("c2", "taxes.csv", "Source B");
const C = item("c3", "accounts.csv", "Source C");

const overview = (confirmedOnly: boolean) => ({
  sources: 3, items: 3, relations: confirmedOnly ? 1 : 2, cross_connection_relations: 2, unconnected_items: confirmedOnly ? 1 : 0,
  all_items: [A, B, C],
  groups: confirmedOnly
    ? [{ size: 2, spans_connections: true, items: [A, B] }]
    : [{ size: 3, spans_connections: true, items: [A, B, C] }],
});

function neighborhood(hops: number, confirmedOnly: boolean) {
  const nodes = [{ ...A, distance: 0, degree: 1, other_connection: false }, { ...B, distance: 1, degree: 2, other_connection: true }];
  const edges = [{ source: "c1||parcels.csv", target: "c2||taxes.csv", link_id: "1", source_column: "parcel_id", target_column: "parcel_id", kind: "guessed", status: confirmedOnly ? "confirmed" : "guessed", sample_based: false, cross_connection: true }];
  if (hops >= 2 && !confirmedOnly) {
    nodes.push({ ...C, distance: 2, degree: 1, other_connection: true });
    edges.push({ source: "c2||taxes.csv", target: "c3||accounts.csv", link_id: "2", source_column: "account_no", target_column: "account_no", kind: "guessed", status: "guessed", sample_based: false, cross_connection: true });
  }
  return { found: true, nodes, edges };
}

function install(options: { available?: boolean; fail?: boolean; items?: boolean } = {}) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      calls.push(String(url));
      const u = new URL(String(url), "http://x");
      const confirmed = u.searchParams.get("confirmed_only") === "true";
      let body: unknown = {};
      if (options.fail) return Promise.resolve({ ok: false, json: async () => ({ detail: "The graph store is not reachable." }) });
      if (u.pathname === "/api/graph/status") {
        body = {
          available: options.available ?? true,
          built: true,
          message: options.available === false ? "The relationship graph needs the Kuzu library, which is not available for this Python version." : null,
        };
      } else if (u.pathname.endsWith("/flowchart")) body = {nodes:[],links:[],external_nodes:[]};
      else if (u.pathname === "/api/graph/overview") body = options.items === false ? { ...overview(false), all_items: [], groups: [] } : overview(confirmed);
      else if (u.pathname === "/api/graph/neighborhood") body = neighborhood(Number(u.searchParams.get("hops")), confirmed);
      else if (u.pathname === "/api/graph/path") {
        const to = u.searchParams.get("to_name");
        body = to === "accounts.csv" && !confirmed
          ? { connected: true, path: { length: 2, items: [A, B, C], links: [
              { source_column: "parcel_id", target_column: "parcel_id", kind: "guessed", status: "guessed", cross_connection: true },
              { source_column: "account_no", target_column: "account_no", kind: "guessed", status: "guessed", cross_connection: true }] } }
          : { connected: false, path: null };
      }
      return Promise.resolve({ ok: true, json: async () => body });
    })
  );
  return calls;
}

function open(path = "/connections/c1/graph") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/connections/:connectionId/graph" element={<RelationshipGraph />} />
        <Route path="/connections/:connectionId/flowchart" element={<p>Flowchart page</p>} />
        <Route path="/connections/:connectionId/items" element={<p>Item page</p>} />
      </Routes>
    </MemoryRouter>
  );
}

const nodeNames = () =>
  drawn[drawn.length - 1].elements.filter((e) => !("source" in e.data)).map((e) => String(e.data.label).split("\n")[0]);

describe("states", () => {
  it("shows a skeleton while loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const { container } = open();
    expect(container.querySelector(".skeleton")).not.toBeNull();
  });

  it("shows an error with Retry", async () => {
    install({ fail: true });
    open();
    expect((await screen.findByRole("alert")).textContent).toContain("not reachable");
    expect(screen.getByRole("button", { name: "Retry" })).toBeDefined();
  });

  it("explains plainly (no error) when the graph is unavailable, and links back to the flowchart", async () => {
    install({ available: false });
    open();
    expect(await screen.findByText("Connection flowchart")).toBeDefined();
    expect(screen.getByText(/Advanced path queries are unavailable/)).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("has an empty state before anything is scanned", async () => {
    install({ items: false });
    open();
    expect(await screen.findByText("Nothing to show yet")).toBeDefined();
  });
});

describe("neighbourhood, path and groups", () => {
  it("starts from the item the user arrived from and draws its neighbourhood", async () => {
    const calls = install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    await waitFor(() => expect(drawn.length).toBeGreaterThan(0));
    expect(calls.some((c) => c.includes("/api/graph/neighborhood") && c.includes("name=parcels.csv") && c.includes("hops=2"))).toBe(true);
    expect(nodeNames()).toEqual(["parcels.csv", "taxes.csv", "accounts.csv"]);
    // the most-connected item is drawn larger
    const elements = drawn[drawn.length - 1].elements;
    const size = (name: string) => Number(elements.find((e) => String(e.data.label).startsWith(name))?.data.size);
    expect(size("taxes.csv")).toBeGreaterThan(size("parcels.csv"));
  });

  it("changes the reach with the stepper", async () => {
    const calls = install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    await waitFor(() => expect(drawn.length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "More links" }));
    await waitFor(() => expect(calls.some((c) => c.includes("hops=3"))).toBe(true));
    expect(screen.getByLabelText("Reachable within").textContent).toBe("3");
  });

  it("Confirmed links only changes the data asked for, so groups and drawing change, not just the styling", async () => {
    const calls = install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    expect(await screen.findByText("3 items · crosses connections")).toBeDefined();
    fireEvent.click(screen.getByLabelText("Confirmed links only"));
    expect(await screen.findByText("2 items · crosses connections")).toBeDefined();
    expect(calls.some((c) => c.includes("/overview") && c.includes("confirmed_only=true"))).toBe(true);
    expect(calls.some((c) => c.includes("/neighborhood") && c.includes("confirmed_only=true"))).toBe(true);
    await waitFor(() => expect(nodeNames()).toEqual(["parcels.csv", "taxes.csv"]));
  });

  it("finds the shortest path and lists the matching column on each link", async () => {
    install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    await screen.findByText("3 items · crosses connections");
    fireEvent.change(screen.getAllByRole("combobox")[1], { target: { value: "c3||accounts.csv" } });
    const list = await screen.findByRole("list", { name: "Path" });
    const text = within(list).getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(text[0]).toContain("parcels.csv");
    expect(text[0]).toContain("via parcel_id (guessed)");
    expect(text[1]).toContain("via account_no (guessed)");
    expect(text[2]).toContain("accounts.csv");
    // highlighted along its edges on the canvas
    await waitFor(() => expect(drawn[drawn.length - 1].elements.filter((e) => e.classes === "on-path").length).toBeGreaterThan(0));
  });

  it("says so when two items are not connected", async () => {
    install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    await screen.findByText("3 items · crosses connections");
    fireEvent.change(screen.getAllByRole("combobox")[1], { target: { value: "c2||taxes.csv" } });
    expect(await screen.findByText(/aren't connected/)).toBeDefined();
  });

  it("clicking an item on the canvas opens its detail page", async () => {
    install();
    open("/connections/c1/graph?schema=&name=parcels.csv");
    await waitFor(() => expect(tapNode).not.toBeNull());
    tapNode!({ target: { data: () => ({ connection_id: "c2", schema: "", name: "taxes.csv" }) } });
    expect(await screen.findByText("Item page")).toBeDefined();
  });

  it("clicking a group jumps to its first item", async () => {
    const calls = install();
    open("/connections/c1/graph");
    fireEvent.click(await screen.findByRole("button", { name: /3 items/ }));
    await waitFor(() => expect(calls.some((c) => c.includes("/neighborhood"))).toBe(true));
  });
});
