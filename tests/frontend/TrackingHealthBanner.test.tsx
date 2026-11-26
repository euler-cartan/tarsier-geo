import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import TrackingHealthBanner from "../../frontend/src/components/TrackingHealthBanner";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("reviews the observed value through its dedicated endpoint and restores warning for a new failure", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true }); vi.stubGlobal("fetch", fetch);
  const done = vi.fn();
  const health = { status: "degraded", logging_failures: 2, logger_version: "fail_open_v1", missing_trigger_count: 0 };
  const view = render(<TrackingHealthBanner connectionId="c" health={health} onReviewed={done} />);
  await userEvent.click(screen.getByRole("button", { name: "Mark as reviewed" }));
  expect(fetch.mock.calls[0][0]).toBe("/api/connections/c/changes/acknowledge");
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ acknowledge_failures_up_to: 2 });
  expect(done).toHaveBeenCalledOnce();
  const reviewed = { ...health, acknowledged_failures: 2, acknowledged_at: "2026-10-18T00:00:00Z" };
  view.rerender(<TrackingHealthBanner connectionId="c" health={reviewed} onReviewed={done} />);
  expect(screen.getByRole("status").textContent).toContain("this does not mean the missing changes were recovered.");
  view.rerender(<TrackingHealthBanner connectionId="c" health={{...reviewed, logging_failures: 3}} onReviewed={done} />);
  expect(screen.getByRole("alert").textContent).toContain("Some changes may be missing");
});

it("does not suppress missing-trigger and outdated-logger warnings after review", () => {
  render(<TrackingHealthBanner connectionId="c" health={{status:"degraded",logging_failures:2,acknowledged_failures:2,acknowledged_at:"2026-10-18T00:00:00Z",missing_trigger_count:1,logger_version:"legacy_or_modified"}} onReviewed={() => {}} />);
  expect(screen.getByRole("alert").textContent).toContain("Change tracking needs an update.");
  expect(screen.getByRole("alert").textContent).toContain("one or more tracking triggers are missing.");
});
