/** TRS-099 / TRS-100 — the stylesheet keeps the 1280px floor, 40px hit targets and a visible keyboard focus ring. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "../../frontend/src/tokens.css"), "utf-8");

describe("desktop layout rules (FSD §16)", () => {
  it("never squeezes the shell below the 1280px minimum width", () => {
    expect(css).toMatch(/html,\s*body\s*\{\s*min-width:\s*1280px/);
  });

  it("gives buttons and text inputs a 40px minimum hit target", () => {
    expect(css).toMatch(/\.button-primary-dark,\s*\.button-secondary-outline\s*\{[^}]*min-height:\s*40px/);
    expect(css).toMatch(/\.text-input\s*\{[^}]*min-height:\s*44px/);
    expect(css).toMatch(/border-radius:\s*var\(--radius-pill\)/); // v2: every button is a pill
  });

  it("draws a visible ink focus ring for keyboard users", () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--ink\)/);
  });

  it("lets dense content scroll sideways instead of clipping", () => {
    expect(css).toMatch(/main\s*\{\s*overflow-x:\s*auto/);
  });
});
