import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Automations from "../../frontend/src/screens/Automations";
import { AiProvider, useAi } from "../../frontend/src/shell/AiContext";

const CATALOG = {
  triggers: [{ id: "any_change", label: "On any change" }],
  conditions: [{ id: "user_eq", label: "If user = X" }],
  actions: [{ id: "log", label: "Write to log" }],
  templates: [{ id: "mass_delete", title: "Notify me on mass delete", blurb: "When a mass delete is captured." }],
};

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function DraftButton() {
  const ai = useAi();
  return (
    <button type="button" onClick={() => ai.notifyDraft()}>
      Apply draft
    </button>
  );
}

describe("Automations screen", () => {
  it("opens a template into the canvas", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).includes("/catalog")) {
          return { ok: true, json: async () => CATALOG };
        }
        if (String(url).includes("/templates/")) {
          return {
            ok: true,
            json: async () => ({
              id: "a1",
              title: "Notify me on mass delete",
              graph: {
                nodes: [
                  { id: "t1", role: "trigger", kind: "any_change", config: { mass_only: true } },
                  { id: "a1", role: "action", kind: "log", config: {} },
                ],
                edges: [{ from: "t1", to: "a1" }],
              },
              paused: false,
              last_run_at: null,
            }),
          };
        }
        return { ok: true, json: async () => ({ automations: [], runs: [] }) };
      })
    );
    render(
      <MemoryRouter initialEntries={["/connections/c1/automations"]}>
        <AiProvider>
          <Routes>
            <Route path="/connections/:connectionId/automations" element={<Automations />} />
          </Routes>
        </AiProvider>
      </MemoryRouter>
    );
    expect(await screen.findByRole("heading", { name: "Automations" })).toBeDefined();
    await user.click(screen.getByRole("button", { name: /Notify me on mass delete/ }));
    expect(await screen.findByRole("button", { name: "Test run" })).toBeDefined();
    expect(screen.getAllByText("On any change").length).toBeGreaterThan(0);
  });

  it("loads an AI draft onto the canvas without leaving the page", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/catalog")) {
          return { ok: true, json: async () => CATALOG };
        }
        return { ok: true, json: async () => ({ automations: [], runs: [] }) };
      })
    );
    render(
      <MemoryRouter initialEntries={["/connections/c1/automations"]}>
        <AiProvider>
          <DraftButton />
          <Routes>
            <Route path="/connections/:connectionId/automations" element={<Automations />} />
          </Routes>
        </AiProvider>
      </MemoryRouter>
    );
    expect(await screen.findByRole("heading", { name: "Automations" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Test run" })).toBeNull();
    sessionStorage.setItem(
      "tarsier-auto-draft-c1",
      JSON.stringify({
        title: "Evening change summary",
        graph: {
          nodes: [
            { id: "t1", role: "trigger", kind: "schedule", config: { hour: 18 } },
            { id: "a1", role: "action", kind: "log", config: {} },
          ],
          edges: [{ from: "t1", to: "a1" }],
        },
      })
    );
    await user.click(screen.getByRole("button", { name: "Apply draft" }));
    expect(await screen.findByRole("button", { name: "Test run" })).toBeDefined();
    expect(screen.getByDisplayValue("Evening change summary")).toBeDefined();
  });
});
