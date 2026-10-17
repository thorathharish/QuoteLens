import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeSelect } from "@/components/theme";
import { themeBootScript } from "@/lib/theme";

function mockSystemDark(dark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({ matches: dark, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  );
}

/** Node 25 ships its own partial localStorage global, which shadows jsdom's: use a plain one. */
function stubStorage() {
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, String(v)),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
  });
}

beforeEach(() => {
  stubStorage();
  delete document.documentElement.dataset.theme;
  mockSystemDark(false);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("theme", () => {
  it("applies and remembers a forced theme, and forgets it on System", () => {
    render(<ThemeSelect />);
    const select = screen.getByLabelText("Theme");
    fireEvent.change(select, { target: { value: "dark" } });
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("quotelens.theme")).toBe("dark");
    fireEvent.change(select, { target: { value: "system" } });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("quotelens.theme")).toBeNull();
  });

  it("boot script resolves System from the OS before paint", () => {
    mockSystemDark(true);
    new Function(themeBootScript())();
    expect(document.documentElement.dataset.theme).toBe("dark");
    localStorage.setItem("quotelens.theme", "light");
    new Function(themeBootScript())();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
