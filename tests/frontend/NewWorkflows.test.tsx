import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Automations from "../../frontend/src/screens/Automations";
import { AiProvider } from "../../frontend/src/shell/AiContext";
import Appearance from "../../frontend/src/shell/Appearance";
import CommandPalette from "../../frontend/src/shell/CommandPalette";

afterEach(() => {vi.unstubAllGlobals(); sessionStorage.clear(); document.documentElement.removeAttribute("data-theme");});

it("AI draft preview does not save; saving waits for explicit approval", async () => {
  HTMLDialogElement.prototype.showModal = function() { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function() { this.removeAttribute("open"); };
  const graph = {nodes: [{id: "t", role: "trigger", kind: "any_change", config: {}}, {id: "a", role: "action", kind: "log", config: {}}], edges: [{from: "t", to: "a"}]};
  sessionStorage.setItem("tarsier-auto-draft-c1", JSON.stringify({title: "AI draft", graph}));
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => ({ok: true, json: async () => url.includes("/catalog") ? {triggers: [], conditions: [], actions: [], templates: []} : url.endsWith("/preview") ? {trace: [], ok: true, dry_run: true} : init?.method === "POST" ? {id: "saved", title: "AI draft", graph} : {automations: [], runs: []}}));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/connections/c1/automations"]}><AiProvider><Routes><Route path="/connections/:connectionId/automations" element={<Automations />} /></Routes></AiProvider></MemoryRouter>);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", {name: "Test run"}));
  expect(fetcher.mock.calls.some(([url, init]) => url.endsWith("/automations") && init?.method === "POST")).toBe(false);
  await user.click(screen.getByRole("button", {name: "Save", exact: true}));
  expect(screen.getByRole("dialog")).toBeDefined();
  expect(fetcher.mock.calls.some(([url, init]) => url.endsWith("/automations") && init?.method === "POST")).toBe(false);
  await user.click(screen.getByRole("button", {name: "Approve & save"}));
  await waitFor(() => expect(fetcher.mock.calls.some(([url, init]) => url.endsWith("/automations") && JSON.parse(String(init?.body || "{}" )).review_approved)).toBe(true));
});

it("applies a saved dark theme and persists a theme switch", async () => {
  const fetcher = vi.fn(async () => ({ok: true, json: async () => ({theme: "dark"})}));
  vi.stubGlobal("fetch", fetcher);
  render(<Appearance />);
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
  await userEvent.click(screen.getByRole("radio", {name: "Light"}));
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
});

it("command palette opens with Ctrl K and navigates to a cached item", async () => {
  HTMLDialogElement.prototype.showModal = function() { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function() { this.removeAttribute("open"); };
  vi.stubGlobal("fetch", vi.fn(async () => ({ok: true, json: async () => [{label: "Example / pipes", url: "/pipes"}]})));
  render(<MemoryRouter><CommandPalette /><Routes><Route path="/pipes" element={<p>Pipe details</p>} /></Routes></MemoryRouter>);
  fireEvent.keyDown(window, {key: "k", ctrlKey: true});
  await userEvent.click(await screen.findByRole("button", {name: /Example \/ pipes/}));
  expect(await screen.findByText("Pipe details")).toBeDefined();
});
