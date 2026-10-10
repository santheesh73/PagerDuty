import { useCallback, useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
const KEY = "pulse.theme";

function systemTheme(): "light" | "dark" {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* storage can be unavailable (private mode); fall back to the system theme */
  }
  return "system";
}

export function applyTheme(preference: ThemePreference = readPreference()): void {
  const resolved = preference === "system" ? systemTheme() : preference;
  document.documentElement.dataset.theme = resolved;
}

export function useTheme(): [ThemePreference, (next: ThemePreference) => void] {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);

  useEffect(() => {
    applyTheme(preference);
    if (preference !== "system") return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    media?.addEventListener("change", onChange);
    return () => media?.removeEventListener("change", onChange);
  }, [preference]);

  const update = useCallback((next: ThemePreference) => {
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* non-fatal */
    }
    setPreference(next);
  }, []);

  return [preference, update];
}
