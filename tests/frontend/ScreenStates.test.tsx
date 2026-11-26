/** TRS-098 — every data-bearing screen shows loading, error (with retry) and empty states, not just the happy path. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Alerts from "../../frontend/src/screens/Alerts";
import Automations from "../../frontend/src/screens/Automations";
import Changes from "../../frontend/src/screens/Changes";
import ConnectionList from "../../frontend/src/screens/ConnectionList";
import Flowchart from "../../frontend/src/screens/Flowchart";
import GlobalStatistics from "../../frontend/src/screens/GlobalStatistics";
import ItemDetail from "../../frontend/src/screens/ItemDetail";
import Overview from "../../frontend/src/screens/Overview";

vi.mock("../../frontend/src/components/MapPreview", () => ({ default: () => <div>Map preview</div> }));

afterEach(() => vi.unstubAllGlobals());

const SCREENS: { name: string; path: string; route: string; element: JSX.Element }[] = [
  { name: "Connection list", path: "/", route: "/", element: <ConnectionList /> },
  { name: "Overview", path: "/connections/c1/overview", route: "/connections/:connectionId/overview", element: <Overview /> },
  { name: "Item detail", path: "/connections/c1/items?schema=&name=roads", route: "/connections/:connectionId/items", element: <ItemDetail /> },
  { name: "Alerts", path: "/connections/c1/alerts", route: "/connections/:connectionId/alerts", element: <Alerts /> },
  { name: "Automations", path: "/connections/c1/automations", route: "/connections/:connectionId/automations", element: <Automations /> },
  { name: "Changes", path: "/connections/c1/changes", route: "/connections/:connectionId/changes", element: <Changes /> },
  { name: "Statistics summary", path: "/connections/c1/statistics", route: "/connections/:connectionId/statistics", element: <GlobalStatistics /> },
  { name: "Flowchart", path: "/connections/c1/flowchart", route: "/connections/:connectionId/flowchart", element: <Flowchart /> },
];

function renderScreen(screen_: (typeof SCREENS)[number]) {
  return render(
    <MemoryRouter initialEntries={[screen_.path]}>
      <Routes>
        <Route path={screen_.route} element={screen_.element} />
      </Routes>
    </MemoryRouter>
  );
}

describe("loading state", () => {
  for (const screenCase of SCREENS) {
    it(`${screenCase.name} shows placeholders while the first request is pending`, () => {
      vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
      const { container } = renderScreen(screenCase);
      expect(container.querySelector(".skeleton, [aria-busy='true']")).not.toBeNull();
    });
  }
});

describe("error state", () => {
  for (const screenCase of SCREENS) {
    it(`${screenCase.name} shows a plain-language error with a Retry that refetches`, async () => {
      const fetchMock = vi.fn(() =>
        Promise.resolve({ ok: false, status: 500, json: async () => ({ detail: "The source is not reachable." }) })
      );
      vi.stubGlobal("fetch", fetchMock);
      renderScreen(screenCase);
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toContain("The source is not reachable.");
      const retry = screen.getByRole("button", { name: "Retry" });
      const before = fetchMock.mock.calls.length;
      fireEvent.click(retry);
      await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    });
  }
});

describe("empty state", () => {
  it("Connection list invites the first connection", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, json: async () => [] })));
    renderScreen(SCREENS[0]);
    expect(await screen.findByRole("link", { name: "Add a connection" })).toBeDefined();
  });

  it("Alerts explains there are none yet", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ rules: [], kinds: [], fires: [] }) }))
    );
    renderScreen(SCREENS[3]);
    expect(await screen.findByText("No alerts yet")).toBeDefined();
  });

  it("Item detail offers a way forward when the item was never scanned", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: "This item hasn't been scanned yet." }) })
      )
    );
    renderScreen(SCREENS[2]);
    expect(await screen.findByText("This item hasn't been checked yet")).toBeDefined();
    expect(screen.getByRole("link", { name: /run a check/i })).toBeDefined();
  });

  it("Statistics summary explains when nothing has been scanned", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ connection_id: "c1", layers: [] }) }))
    );
    renderScreen(SCREENS[6]);
    expect(await screen.findByText("No layers have been scanned yet")).toBeDefined();
  });
});

describe("partial / not-applicable state", () => {
  it("Changes says tracking is unavailable (not an error) for file connections", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          json: async () => ({ available: false, reason: "Change tracking isn't available for file connections.", events: [], volume: [] }),
        })
      )
    );
    renderScreen(SCREENS[5]);
    expect(await screen.findByText(/isn't available for file connections/)).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
