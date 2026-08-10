"use client";

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "tradingos-theme";

type Theme = "light" | "dark";

// The `.dark` class only ever changes through `setTheme` below (our own
// click handler) or the `beforeInteractive` script in app/layout.tsx
// (which runs before this component ever mounts) — so a real DOM
// MutationObserver isn't needed; this module-level listener set is
// enough to satisfy `useSyncExternalStore`'s subscribe contract.
const listeners = new Set<() => void>();

function getSnapshot(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

// React uses this during SSR *and* the initial client hydration pass,
// so both produce identical markup — no hydration mismatch, and no
// mount-effect needed to "fix up" the theme after the fact (which is
// what the lint rule below would otherwise flag as a cascading render).
function getServerSnapshot(): Theme {
  return "light";
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function setTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  window.localStorage.setItem(STORAGE_KEY, theme);
  listeners.forEach((listener) => listener());
}

/**
 * Manual dark/light switcher (Revision Prompt 15 — "provide dark/light
 * themes", not merely "respect the OS setting"). Every `dark:` utility
 * in this app already keys off the `.dark` class (see app/globals.css's
 * `@custom-variant dark`) — this component only needs to toggle that
 * class, no other file changes.
 */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      data-testid="theme-toggle"
      className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
    >
      <span aria-hidden="true">{theme === "dark" ? "\u{1F319}" : "\u{2600}\u{FE0F}"}</span>
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}
