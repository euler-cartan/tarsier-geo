import { render, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import Changes from "../../frontend/src/screens/Changes";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("preserves UTC calendar dates in a New York browser runtime", async () => {
  expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("America/New_York");
  const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({available:true,mode:"triggers",reason:null,events:[],volume:[],report:null})});
  vi.stubGlobal("fetch",fetch);
  const {container}=render(<MemoryRouter initialEntries={["/connections/c/changes"]}><Routes><Route path="/connections/:connectionId/changes" element={<Changes />} /></Routes></MemoryRouter>);
  await waitFor(()=>expect(container.querySelectorAll('input[type="date"]').length).toBe(2));
  const inputs=container.querySelectorAll('input[type="date"]');
  // Midnight UTC is the previous local evening. The selected UTC day must
  // remain the calendar string, never a local-day conversion of that instant.
  expect(new Date("2026-10-18T00:00:00Z").getDate()).toBe(17);
  fireEvent.change(inputs[0],{target:{value:"2026-10-18"}});
  fireEvent.change(inputs[1],{target:{value:"2026-10-18"}});
  // The measured UI applies the chosen dates on explicit form submission.
  fireEvent.submit(container.querySelector("form")!);
  await waitFor(()=>expect(fetch.mock.calls.some(call=>String(call[0]).includes("start=2026-10-18&end=2026-10-18"))).toBe(true));
});
