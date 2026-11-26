import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Overview from "../../frontend/src/screens/Overview";

const NEVER_SCANNED = {
  connection_id: "c1",
  connection_name: "Test DB",
  connection_type: "postgis",
  last_scanned_at: null,
  ever_scanned: false,
  total_layers: 0,
  relationship_count: 0,
  total_size_bytes: null,
  health_score: null,
  health_coverage_count: 0,
  health_components: { quality: null, freshness: null, completeness: null },
  layers: [],
  projections: [],
};

const SCANNED = {
  ...NEVER_SCANNED,
  ever_scanned: true,
  last_scanned_at: "2026-01-01T00:00:00Z",
  total_layers: 1,
  relationship_count: 2,
  total_size_bytes: 2048,
  health_score: 75,
  health_coverage_count: 1,
  health_components: { quality: 80, freshness: 70, completeness: 60 },
  layers: [
    {
      schema: "public", name: "water_mains", kind: "vector", geometry_type: "LineString", srid: 4326,
      row_count: 2, row_count_is_estimate: true, size_bytes: 2048, has_index: true,
      last_modified: null, is_stale: false, is_heavy: false,
      health_score: 61, health_components: { quality: 70, freshness: 50, completeness: 60 },
    },
  ],
  projections: [{ srid: 4326, layer_count: 1, is_majority: true }],
};

function renderOverview(progress = false) {
  if (!progress) {
    const fetcher = globalThis.fetch;
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => url.endsWith("/checks") ? Promise.resolve({ok:true,json:async()=>({state:"idle"})}) : fetcher(url,init));
  }
  return render(
    <MemoryRouter initialEntries={["/connections/c1/overview"]}>
      <Routes>
        <Route path="/connections/:connectionId/overview" element={<Overview />} />
      </Routes>
    </MemoryRouter>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Overview page", () => {
  it("shows each large table whose full statistics used a sample", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, json: async () =>
      url.endsWith("/checks")
        ? { state: "completed", completed: 1, total: 1, message: "Health check complete.", skipped: [{ schema: "public", name: "wide", check: "statistics", message: "skipped: too large for full check; sample used" }] }
        : SCANNED
    })));
    renderOverview(true);
    expect(await screen.findByText("public.wide: skipped: too large for full check; sample used")).toBeDefined();
  });
  it("shows a skeleton while loading, shaped like the real layout (FSD §15)", async () => {
    let resolveFetch: (value: unknown) => void;
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));

    renderOverview();

    const skeleton = screen.getByLabelText("Loading overview");
    expect(skeleton.getAttribute("aria-busy")).toBe("true");
    // Shaped like the real table: same column headers, just shimmering rows.
    expect(screen.getByText("Projection")).toBeDefined();

    resolveFetch!({ ok: true, json: async () => NEVER_SCANNED });
    expect(await screen.findByText("No check has run yet for this connection.")).toBeDefined();
    expect(screen.queryByLabelText("Loading overview")).toBeNull();
  });

  it("shows the never-scanned empty state with a Run first check action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => NEVER_SCANNED }));
    renderOverview();

    expect(await screen.findByText("No check has run yet for this connection.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Run first check" })).toBeDefined();
  });

  it("shows headline stats and the layer table once scanned", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => SCANNED }));
    renderOverview();

    expect(await screen.findByText("water_mains")).toBeDefined();
    expect(screen.getByText("Test DB")).toBeDefined();
    expect(screen.getByText("2 connections found.")).toBeDefined();
    expect(screen.getByLabelText(/Health score 75/)).toBeDefined();
    expect(screen.getByLabelText(/Health score 61/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Open full flowchart →" }).getAttribute("href")).toBe("/connections/c1/flowchart");
    expect(screen.getAllByText("2.0 KB").length).toBeGreaterThan(0); // total size stat + the layer's own size
  });

  it("labels a partial connection health score with its coverage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      ...SCANNED, health_score: 0, total_layers: 31, health_coverage_count: 2,
    }) }));
    renderOverview();
    expect(await screen.findByText("0, based on 2 of 31 items")).toBeDefined();
  });

  it("shows a plain-language error with a Retry action, and Retry recovers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: "No such connection." }) })
      .mockResolvedValueOnce({ ok: true, json: async () => NEVER_SCANNED });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderOverview();

    expect(await screen.findByText("No such connection.")).toBeDefined();
    const retry = screen.getByRole("button", { name: "Retry" });

    await user.click(retry);

    expect(await screen.findByText("No check has run yet for this connection.")).toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shows full-check progress and reloads results when the job completes", async () => {
    let started=false, completed=false;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => ({ok:true,json:async()=> {
      if (url.endsWith("/checks")) {
        if (init?.method === "POST") {started=true;return {state:"running",completed:0,total:5,message:"Health results will appear shortly."};}
        if (started) {completed=true;return {state:"completed",completed:5,total:5,message:"Health check complete. Results are ready."};}
        return {state:"idle"};
      }
      return completed ? SCANNED : NEVER_SCANNED;
    }}));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderOverview(true);

    const button = await screen.findByRole("button", { name: "Run first check" });
    await user.click(button);

    expect(await screen.findByText("Health results will appear shortly.")).toBeDefined();
    await waitFor(() => expect(screen.getByText("water_mains")).toBeDefined(), {timeout:4000});
    expect(fetchMock.mock.calls.some(([url,init])=>url.endsWith("/checks") && init?.method === "POST")).toBe(true);
  });
});
