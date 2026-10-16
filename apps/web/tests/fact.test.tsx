import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FactValue } from "@/components/fact";

afterEach(cleanup);

describe("FactValue", () => {
  it("shows the value with its provenance", () => {
    render(<FactValue fact={{ value: "153.00", provenance: "CALCULATED", formula: "306 × 0.50", unit: "USD" }} kind="money" />);
    expect(screen.getByRole("button").textContent).toContain("$153.00");
    expect(screen.getByText("Calculated")).toBeTruthy();
    expect(screen.getByRole("button").getAttribute("title")).toContain("306 × 0.50");
  });

  it("never renders an unavailable value as a number", () => {
    render(<FactValue fact={{ value: null, provenance: "UNAVAILABLE", note: "No authorized offer" }} kind="money" />);
    const button = screen.getByRole("button");
    expect(button.textContent).toContain("—");
    expect(button.textContent).not.toMatch(/\d/);
    expect(button.getAttribute("title")).toBe("No authorized offer");
    expect(screen.getByText("Unavailable")).toBeTruthy();
  });

  it("renders a dash when there is no fact at all", () => {
    render(<FactValue fact={null} />);
    expect(screen.getByText("—")).toBeTruthy();
  });
});
