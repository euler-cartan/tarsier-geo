import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Changes from "../../frontend/src/screens/Changes";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Changes screen", () => {
  it("says change tracking is not available for files", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          available: false,
          reason: "Change tracking isn't available for file connections — Tarsier takes no snapshots of files.",
          mode: "none",
          events: [],
          volume: [],
        }),
      })
    );
    render(
      <MemoryRouter initialEntries={["/connections/c1/changes"]}>
        <Routes>
          <Route path="/connections/:connectionId/changes" element={<Changes />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/isn't available for file connections/)).toBeDefined();
  });

  it("filters the feed when a volume bar is conceptually represented by listed events", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          available: true,
          mode: "triggers",
          reason: null,
          report: { total: 2, by_action: { update: 1, delete: 1 }, mass_batches: 1, schema_changes: 0 },
          report_interval: "daily",
          volume: [{ date: "2026-10-10", count: 40, insert: 0, update: 0, delete: 40, schema: 0, is_spike: true }],
          events: [
            {
              id: "e1",
              occurred_at: "2026-10-10T12:00:00Z",
              db_user: "alice",
              action: "delete",
              schema: "public",
              name: "water_mains",
              feature_id: "1",
              before: { material: "PVC" },
              after: null,
              txid: "9",
              source: "trigger",
              is_mass: true,
              changed_fields: ["material"],
            },
          ],
        }),
      })
    );
    render(
      <MemoryRouter initialEntries={["/connections/c1/changes"]}>
        <Routes>
          <Route path="/connections/:connectionId/changes" element={<Changes />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/mass change/)).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Feature 1" }));
    expect(screen.getByRole("heading", { name: "Feature 1" })).toBeDefined();
    expect(screen.getAllByText("material").length).toBeGreaterThan(0);
  });
});
