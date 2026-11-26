import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Flowchart from "../../frontend/src/screens/Flowchart";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(["Scan connections", "Compare with other connections"])("%s displays unknown count without claiming no links", async (action) => {
  const message = "Could not verify 2 candidates. No conclusion about those links was made.";
  vi.stubGlobal("fetch", vi.fn((url: string, options?: RequestInit) => {
    const body = options?.method === "POST"
      ? String(url).includes("/cross/")
        ? { guesses: 0, skipped_connections: [], could_not_verify: 2, message }
        : { nodes: [], links: [], could_not_verify: 2, message }
      : { nodes: [], links: [] };
    return Promise.resolve({ ok: true, json: async () => body });
  }));
  render(<MemoryRouter initialEntries={["/connections/test/flowchart"]}><Routes><Route path="/connections/:connectionId/flowchart" element={<Flowchart />} /></Routes></MemoryRouter>);
  await waitFor(() => expect((screen.getAllByRole("button", { name: action })[0] as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getAllByRole("button", { name: action })[0]);
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain(message));
  expect(screen.getByRole("heading", { name: "Some candidates could not be verified" })).not.toBeNull();
  expect(screen.queryByText("No connections found yet")).toBeNull();
});
