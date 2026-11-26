import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import TopBar from "../../frontend/src/shell/TopBar";

const connection = {
  id: "c1",
  name: "TestingDB",
  type: "postgis",
  config: {},
  last_checked_at: null,
  last_status: "ok",
};

function FinishConnection() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/connections/c1/overview")}>Finish connection setup</button>;
}

afterEach(() => vi.unstubAllGlobals());

describe("TopBar connection switcher", () => {
  it("selects the current database and refreshes connections after setup", async () => {
    let requestCount = 0;
    vi.stubGlobal("fetch", vi.fn(() => {
      const response = requestCount++ === 0 ? [] : [connection];
      return Promise.resolve({ ok: true, json: async () => response });
    }));

    render(
      <MemoryRouter initialEntries={["/connections/new"]}>
        <Routes>
          <Route element={<><TopBar /><Outlet /></>}>
            <Route path="/connections/new" element={<FinishConnection />} />
            <Route path="/connections/:connectionId/:section/*" element={<p>Overview page</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    );

    await screen.findByRole("button", { name: "Finish connection setup" });
    await userEvent.click(screen.getByRole("button", { name: "Finish connection setup" }));

    const switcher = await screen.findByRole("combobox");
    await screen.findByRole("option", { name: "TestingDB (postgis)" });
    expect((switcher as HTMLSelectElement).value).toBe("c1");
  });
});
