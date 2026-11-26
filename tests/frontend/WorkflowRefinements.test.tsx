import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Snapshots from "../../frontend/src/screens/Snapshots";
import Changes from "../../frontend/src/screens/Changes";
import Automations from "../../frontend/src/screens/Automations";

afterEach(() => {vi.unstubAllGlobals(); sessionStorage.clear();});

it("opens snapshot exploration immediately and executes the reviewed filter without another AI call", async () => {
  vi.stubGlobal("scrollTo", vi.fn());
  const filter = {caption: "diameter > 10", combine: "and", conditions: [{column: "diameter", op: ">", value: 10}]};
  const versions = Array.from({length: 120}, (_, i) => ({id: `v${i}`, schema: "public", name: `layer_${i}`, created_at: "2026-10-17T10:00:00", row_count: 100, geospatial: false}));
  const fetcher = vi.fn(async (url: string, _init?: RequestInit) => ({ok: true, json: async () => url.endsWith("/plan") ? {filter, caption: filter.caption} : url.endsWith("/query") ? {count: 1, rows: [{very_long_column_name: "2026-10-17T12:30:00", diameter: 20}], sql: "SELECT * FROM snapshot WHERE diameter > ?", params: [10], filter} : {available: true, versions}}));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/connections/c/snapshots"]}><Routes><Route path="/connections/:connectionId/snapshots" element={<Snapshots />} /></Routes></MemoryRouter>);
  const user = userEvent.setup();
  const buttons = await screen.findAllByRole("button", {name: "Explore"});
  await user.click(buttons[0]);
  expect(screen.queryByRole("button", {name: "Explore"})).toBeNull();
  expect(document.activeElement?.getAttribute("aria-label")).toBe("Snapshot explorer");
  await user.type(screen.getByRole("textbox", {name: "Ask about this snapshot"}), "diameter greater than 10");
  await user.click(screen.getByRole("button", {name: "Review search"}));
  await user.click(await screen.findByRole("button", {name: "Run search"}));
  const results = await screen.findByLabelText("Snapshot search results");
  expect(within(results).getByRole("table").style.minWidth).toBe("700px");
  expect(within(results).getByText("2026-10-17T12:30:00")).toBeDefined();
  const call = fetcher.mock.calls.find(([url]) => url.endsWith("/query"));
  // Inspect the request independently of the response fixture.
  expect(call?.[0]).toContain("/v0/query");
  expect(JSON.parse(String(call?.[1]?.body))).toEqual({filter_payload: filter, bbox: null});
  await user.click(screen.getByRole("button", {name: "Back to snapshots"}));
  expect(screen.getAllByRole("button", {name: "Explore"})).toHaveLength(120);
});

function BrowserBack() {const navigate = useNavigate(); return <button onClick={() => navigate(-1)}>Browser back</button>;}

it("keeps blank canvas first and browser back returns to automation choices", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ok: true, json: async () => url.endsWith("/catalog") ? {triggers: [], conditions: [], actions: [], templates: [{id: "t", title: "Example template", blurb: "Example"}]} : {automations: [], runs: []}})));
  render(<MemoryRouter initialEntries={["/connections/c/automations"]}><BrowserBack /><Routes><Route path="/connections/:connectionId/automations" element={<Automations />} /></Routes></MemoryRouter>);
  const blank = await screen.findByRole("button", {name: /Blank canvas/});
  const templates = blank.parentElement!;
  expect(within(templates).getAllByRole("button")[0]).toBe(blank);
  await userEvent.click(blank);
  expect(screen.getByRole("button", {name: "Back to automations"})).toBeDefined();
  await userEvent.click(screen.getByRole("button", {name: "Browser back"}));
  expect(await screen.findByRole("button", {name: /Blank canvas/})).toBeDefined();
  expect(screen.queryByRole("button", {name: "Test run"})).toBeNull();
});

it("shows report schedule selection and report generation feedback", async () => {
  let interval: string | null = null;
  let generated = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") interval = JSON.parse(String(init.body)).interval;
    if (init?.method === "POST") generated = true;
    return {ok: true, json: async () => ({available: true, mode: "polling", events: [], volume: [], report_interval: interval === "off" ? null : interval, report: generated ? {interval: "daily", total: 3, mass_batches: 0} : null})};
  }));
  render(<MemoryRouter initialEntries={["/connections/c/changes"]}><Routes><Route path="/connections/:connectionId/changes" element={<Changes />} /></Routes></MemoryRouter>);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", {name: "Daily", exact: true}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Daily", exact: true}).getAttribute("aria-pressed")).toBe("true"));
  expect(screen.getByText("Automatic daily reports enabled.")).toBeDefined();
  await user.click(screen.getByRole("button", {name: "Generate now"}));
  expect(await screen.findByText("Report generated from the recorded change log.")).toBeDefined();
  expect(screen.getByText(/3 changes/)).toBeDefined();
  expect(screen.getByLabelText("From")).toBeDefined();
  expect(screen.getByLabelText("Through")).toBeDefined();
});
