import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AddConnection from "../../frontend/src/AddConnection";

const TYPES = [
  { id: "postgis", label: "PostGIS / PostgreSQL", change_tracking: "full", quality_checks: "full", statistics: "full", notice: null },
  { id: "files", label: "Files in folders", change_tracking: "none", quality_checks: "full", statistics: "full", notice: "Files connections don't support change tracking — Tarsier takes no snapshots." },
];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => TYPES })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderWithRouter() {
  return render(
    <MemoryRouter>
      <AddConnection />
    </MemoryRouter>
  );
}

describe("AddConnection tier notices (TRS-007)", () => {
  it("shows the unavailable-features warning before the user can save a files connection", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    const filesButton = await screen.findByRole("button", { name: "Files in folders" });
    await user.click(filesButton);

    const notice = await screen.findByRole("alert");
    expect(notice.textContent).toMatch(/don't support change tracking/i);
  });

  it("shows a positive confirmation, not a warning, for a fully-available type", async () => {
    const user = userEvent.setup();
    renderWithRouter();

    const postgisButton = await screen.findByRole("button", { name: "PostGIS / PostgreSQL" });
    await user.click(postgisButton);

    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeNull();
    });
    expect(screen.getByText(/fully supported/i)).toBeDefined();
    expect(screen.getByText(/install a one-time history log in your database \(needs write permission\)/i)).toBeDefined();
    expect(screen.getByRole("button", { name: "Enable" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Skip for now" })).toBeDefined();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it.each(["Enable", "Skip for now"])("saves first and installs only after %s", async (choice) => {
    const user = userEvent.setup();
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
      requests.push(`${options?.method ?? "GET"} ${url}`);
      if (url === "/api/connections/types") return { ok: true, json: async () => TYPES };
      if (url === "/api/connections") return { ok: true, json: async () => ({ id: "saved-1" }) };
      return { ok: true, json: async () => ({ status: "ok" }) };
    }));
    renderWithRouter();
    await user.click(await screen.findByRole("button", { name: "PostGIS / PostgreSQL" }));
    await user.type(screen.getByRole("textbox", { name: "Connection name" }), "Disposable");
    await user.type(screen.getByRole("textbox", { name: "Host" }), "127.0.0.1");
    await user.type(screen.getByRole("textbox", { name: "Database" }), "disposable");
    await user.type(screen.getByRole("textbox", { name: "Username" }), "tester");
    await user.click(screen.getByRole("button", { name: choice }));
    expect(screen.getByRole("button", { name: choice }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: choice }).className).toContain("button-primary-dark");
    await user.click(screen.getByRole("button", { name: "Test & save" }));
    await waitFor(() => expect(requests).toContain("POST /api/connections"));
    await waitFor(() => expect(screen.getByText("Connection saved.")).toBeDefined());
    expect(requests.filter((r) => r.startsWith("POST"))).toEqual(choice === "Enable"
      ? ["POST /api/connections", "POST /api/connections/saved-1/changes/install-triggers"]
      : ["POST /api/connections"]);
  });
});
