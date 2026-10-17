"use client";

import { useEffect, useState } from "react";
import { applyTheme, DARK_QUERY, readTheme, type ThemeChoice } from "@/lib/theme";

/** Theme choice: follow the system, or force light or dark. */
export function ThemeSelect({ compact = false }: { compact?: boolean }) {
  const [choice, setChoice] = useState<ThemeChoice>("system");

  useEffect(() => setChoice(readTheme()), []);

  // While on "system", follow the OS when it switches (e.g. at sunset).
  useEffect(() => {
    if (choice !== "system") return;
    const media = window.matchMedia(DARK_QUERY);
    const follow = () => applyTheme("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [choice]);

  return (
    <label className="flex items-center gap-2">
      <span className={compact ? "sr-only" : "label"}>Theme</span>
      <select
        value={choice}
        onChange={(e) => {
          const next = e.target.value as ThemeChoice;
          setChoice(next);
          applyTheme(next);
        }}
        className="chip rounded-md px-2 py-1.5 text-sm text-ink"
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
