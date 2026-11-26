import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../frontend/src/App";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App shell", () => {
  it("renders the sidebar heading on every screen", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Tarsier" })).toBeDefined();
  });

  it("shows the welcome panel when there are no connections", async () => {
    render(<App />);
    expect(await screen.findByText("Connect your first database.")).toBeDefined();
  });
});
