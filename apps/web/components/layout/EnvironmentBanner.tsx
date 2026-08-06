"use client";

import { useOperatingMode } from "@/lib/hooks/useOperatingMode";
import type { EnvironmentLabel } from "@/lib/api/operatingMode";

const ENVIRONMENT_COPY: Record<EnvironmentLabel, { text: string; classes: string }> = {
  RESEARCH: {
    text: "RESEARCH — read-only, no orders can be submitted",
    classes: "bg-zinc-800 text-zinc-100 dark:bg-zinc-200 dark:text-zinc-900",
  },
  PAPER: {
    text: "PAPER — simulated orders only, no real money",
    classes: "bg-blue-700 text-white dark:bg-blue-500 dark:text-black",
  },
  LIVE: {
    text: "LIVE — real orders, real money",
    classes: "bg-red-700 text-white dark:bg-red-500 dark:text-black",
  },
};

/**
 * PROJECT_INSTRUCTIONS.md v2 amendment: a persistent environment banner
 * that cannot be hidden by a query parameter. This component
 * deliberately never reads `useSearchParams()`, `window.location`, or
 * any other URL-derived value — there is no code path here a query
 * string could reach, which is what "cannot be hidden by a query
 * parameter" means in practice: not a check that's merely absent today,
 * but a component with no mechanism to add one to by accident. Its
 * value always comes from `useOperatingMode()` (the API), never client
 * storage, and it renders in every state (loading/error included) —
 * never unmounts itself.
 */
export function EnvironmentBanner() {
  const { data, isLoading, isError } = useOperatingMode();

  if (isLoading) {
    return (
      <div
        role="status"
        data-testid="environment-banner"
        className="w-full bg-zinc-600 px-3 py-1.5 text-center text-xs font-semibold tracking-wide text-white dark:bg-zinc-700"
      >
        Checking environment&hellip;
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div
        role="alert"
        data-testid="environment-banner"
        className="w-full bg-amber-700 px-3 py-1.5 text-center text-xs font-semibold tracking-wide text-white dark:bg-amber-600"
      >
        ENVIRONMENT UNKNOWN — API unreachable, treat as RESEARCH (no orders can be submitted)
      </div>
    );
  }

  const copy = ENVIRONMENT_COPY[data.environment_label];
  return (
    <div
      role="status"
      data-testid="environment-banner"
      className={`w-full px-3 py-1.5 text-center text-xs font-semibold tracking-wide ${copy.classes}`}
    >
      {copy.text}
    </div>
  );
}
