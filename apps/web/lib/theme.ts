/** Theme choice shared by the boot script (server-rendered) and the theme select (client). */

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_KEY = "quotelens.theme";
export const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * Inline <head> script: sets data-theme="light|dark" on <html> before first paint, so the
 * page never flashes the wrong theme. "system" is resolved from the OS here.
 */
export function themeBootScript(): string {
  return `(function(){try{var c=localStorage.getItem("${THEME_KEY}")||"system";var d=c==="dark"||(c==="system"&&matchMedia("${DARK_QUERY}").matches);document.documentElement.dataset.theme=d?"dark":"light";}catch(e){document.documentElement.dataset.theme="light";}})();`;
}

export function readTheme(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  const dark = choice === "dark" || (choice === "system" && window.matchMedia(DARK_QUERY).matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage blocked (private mode): the theme still applies for this page view.
  }
}
