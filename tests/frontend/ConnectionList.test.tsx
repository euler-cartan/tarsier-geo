import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import ConnectionList from "../../frontend/src/screens/ConnectionList";

const connections = [
  { id: "partial", name: "Limited role", type: "postgis", config: {}, last_checked_at: null, last_status: null },
  { id: "full", name: "Complete role", type: "postgis", config: {}, last_checked_at: null, last_status: null },
  { id: "empty", name: "Unavailable role", type: "postgis", config: {}, last_checked_at: null, last_status: null },
];

function summary(score: number | null, coverage: number, total: number) {
  return { health_score: score, health_coverage_count: coverage, total_layers: total };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

describe("connection card health badges", () => {
  it.each(["light", "dark"])("shows score and partial coverage consistently in %s theme", async (theme) => {
    document.documentElement.dataset.theme = theme;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
      ok: true,
      json: async () => url === "/api/connections" ? connections : url.includes("/partial/") ? summary(0, 2, 31) : url.includes("/full/") ? summary(90, 31, 31) : summary(null, 0, 0),
    })));

    const { container } = render(<MemoryRouter><ConnectionList /></MemoryRouter>);

    expect(await screen.findByText("0, based on 2 of 31 items")).toBeDefined();
    expect(screen.getByLabelText(/Health score 90/)).toBeDefined();
    expect(screen.queryByText(/90, based on/)).toBeNull();
    expect(container.querySelector('[title="No health components are available"]')?.textContent).toBe(" - ");
    expect(container.querySelectorAll(".card")).toHaveLength(3);
  });
});
