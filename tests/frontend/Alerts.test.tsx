import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Alerts from "../../frontend/src/screens/Alerts";

const KINDS = [
  { id: "mass_change", label: "Mass delete / mass edit" },
  { id: "row_count_drop", label: "Row count dropped" },
  { id: "schema_change", label: "Schema changed" },
  { id: "freshness", label: "Layer not updated (freshness)" },
  { id: "quality_score_drop", label: "Quality score dropped" },
  { id: "specific_user", label: "Specific user" },
  { id: "layer_presence", label: "New or dropped layer" },
  { id: "size_spike", label: "Size grew abnormally" },
  { id: "banned_value", label: "Banned value appeared" },
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Alerts screen", () => {
  it("lists every alert type in the create form and can pause a rule", async () => {
    const user = userEvent.setup();
    let paused = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === "PUT") paused = true;
        return {
          ok: true,
          json: async () => ({
            kinds: KINDS,
            fires: [],
            id: "r1",
            kind: "mass_change",
            title: "Mass",
            target_schema: "",
            target_name: "",
            config: {},
            paused,
            last_triggered_at: null,
            last_message: null,
            status: paused ? "paused" : "active",
            rules: [
              {
                id: "r1",
                kind: "mass_change",
                title: "Mass",
                target_schema: "",
                target_name: "",
                config: {},
                paused,
                last_triggered_at: null,
                last_message: null,
                status: paused ? "paused" : "active",
              },
            ],
          }),
        };
      })
    );
    render(
      <MemoryRouter initialEntries={["/connections/c1/alerts"]}>
        <Routes>
          <Route path="/connections/:connectionId/alerts" element={<Alerts />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByRole("heading", { name: "Alerts" })).toBeDefined();
    for (const kind of KINDS) {
      expect(screen.getByRole("option", { name: kind.label })).toBeDefined();
    }
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(await screen.findByText("paused")).toBeDefined();
  });
});


it("keeps IS UNIQUE out of alert operator choices", async () => {
  const user=userEvent.setup();
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,json:async()=>({rules:[],fires:[],kinds:KINDS})})));
  render(<MemoryRouter initialEntries={["/connections/c1/alerts"]}><Routes><Route path="/connections/:connectionId/alerts" element={<Alerts />} /></Routes></MemoryRouter>);
  await screen.findByRole("heading",{name:"Alerts"});
  await user.selectOptions(screen.getAllByRole("combobox")[0],"banned_value");
  const options=screen.getAllByRole("option") as HTMLOptionElement[];
  expect(options.some(option=>option.value==="is_unique")).toBe(false);
  expect(options.some(option=>option.value==="gte")).toBe(true);
});
