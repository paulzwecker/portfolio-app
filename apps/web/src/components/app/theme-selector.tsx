"use client";

import { useEffect, useRef } from "react";

const storageKey = "personal-universe-theme";
type Theme = "system" | "light" | "dark";

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: Theme, darkSystem: boolean) {
  document.documentElement.dataset.theme =
    theme === "system" ? (darkSystem ? "dark" : "light") : theme;
}

export function ThemeSelector() {
  const select = useRef<HTMLSelectElement>(null);
  const selected = useRef<Theme>("system");
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => {
      const theme = readTheme();
      selected.current = theme;
      if (select.current) select.current.value = theme;
      applyTheme(theme, media.matches);
    };
    sync();
    const syncSystem = () => applyTheme(selected.current, media.matches);
    media.addEventListener("change", syncSystem);
    window.addEventListener("storage", sync);
    return () => {
      media.removeEventListener("change", syncSystem);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <label className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
      <span className="hidden sm:inline">Appearance</span>
      <select
        ref={select}
        aria-label="Appearance"
        defaultValue="system"
        className="min-h-9 rounded-md border border-input bg-card px-2 text-xs text-foreground"
        onChange={(event) => {
          const theme = event.currentTarget.value as Theme;
          selected.current = theme;
          try {
            if (theme === "system") localStorage.removeItem(storageKey);
            else localStorage.setItem(storageKey, theme);
          } catch {
            // The selected appearance still applies to this page without storage.
          }
          applyTheme(
            theme,
            window.matchMedia("(prefers-color-scheme: dark)").matches,
          );
        }}
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
