import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

// Also read by the inline script in index.html, which applies the theme before first paint.
const STORAGE_KEY = "settle-theme";

interface ThemeState {
  theme: Theme;
  resolved: ResolvedTheme;
}

const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)");

function readStoredTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

function resolve(theme: Theme): ResolvedTheme {
  if (theme !== "system") return theme;
  return systemDark().matches ? "dark" : "light";
}

const useThemeStore = create<ThemeState>(() => {
  const theme = readStoredTheme();
  return { theme, resolved: resolve(theme) };
});

function apply(theme: Theme) {
  const resolved = resolve(theme);
  document.documentElement.classList.toggle("dark", resolved === "dark");
  useThemeStore.setState({ theme, resolved });
}

export function setTheme(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Storage can be unavailable (private mode); the choice still applies for this visit.
  }
  apply(theme);
}

/** Follows the operating system's setting while the theme is "system". Call once at startup. */
export function watchSystemTheme() {
  const query = systemDark();
  const onChange = () => {
    if (useThemeStore.getState().theme === "system") apply("system");
  };
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useTheme() {
  return useThemeStore((state) => state.theme);
}

export function useResolvedTheme() {
  return useThemeStore((state) => state.resolved);
}
