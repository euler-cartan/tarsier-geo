import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HealthRing from "../../frontend/src/components/HealthRing";

describe("sample health", () => {
  it("labels compact scores visibly and uses a neutral colour", () => {
    const {container}=render(<HealthRing score={100} isSample size="small" />);
    expect(screen.getByText("100 (sample-based)")).toBeDefined();
    expect(screen.getByLabelText(/sample-based; not a full check/)).toBeDefined();
    expect(container.innerHTML).not.toContain("var(--status-good)");
  });
  it("labels aggregate rings and component values", () => {
    render(<HealthRing score={80} isSample componentsAreAverages components={{quality:100,freshness:50,completeness:null}} />);
    expect(screen.getByText("Sample-based; not a full check")).toBeDefined();
    expect(screen.getByLabelText(/sample-based; not a full check/)).toBeDefined();
  });
});
