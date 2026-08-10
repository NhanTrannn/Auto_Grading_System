import { useCallback, useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "autograding2026.theme";

function readStored(): ThemeMode {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === "light" || raw === "dark" ? raw : "system";
}

function apply(mode: ThemeMode) {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
}

/**
 * Theme preference persisted in localStorage. "system" removes the
 * `data-theme` attribute entirely so `prefers-color-scheme` takes over
 * (matching the light/dark blocks in styles/global.css).
 */
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(() => readStored());

  useEffect(() => {
    apply(mode);
    if (mode === "system") localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  const toggle = useCallback(() => {
    setMode((current) => {
      if (current === "system") {
        const systemIsDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        return systemIsDark ? "light" : "dark";
      }
      return current === "dark" ? "light" : "dark";
    });
  }, []);

  const isDark =
    mode === "dark" ||
    (mode === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);

  return { mode, setMode, toggle, isDark };
}
