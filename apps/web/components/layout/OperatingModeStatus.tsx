"use client";

import { useOperatingMode } from "@/lib/hooks/useOperatingMode";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

const MODE_LABEL: Record<string, string> = {
  RESEARCH_ONLY: "Research only",
  PAPER_MANUAL_APPROVAL: "Paper (manual approval)",
  PAPER_AUTO_POLICY: "Paper (auto policy)",
  LIVE_CONFIRM_EACH_ORDER: "Live (confirm each order)",
};

/**
 * ORDER AUTHORITY (PROJECT_INSTRUCTIONS.md v2 amendment): a read-only
 * status readout of the exact `OrderAuthorityMode` value, distinct from
 * `EnvironmentBanner`'s coarser RESEARCH/PAPER/LIVE band. Deliberately
 * **nonfunctional** this pass — it has no control to change the mode
 * (that selector is separate, future scope per docs/UX_MAP.md, and must
 * never widen what the server actually authorizes regardless of what it
 * displays). Value always comes from `useOperatingMode()` (the API).
 */
export function OperatingModeStatus() {
  const { data, isLoading, isError } = useOperatingMode();

  if (isLoading) {
    return <LoadingSpinner label="Loading operating mode…" />;
  }

  if (isError || !data) {
    return (
      <span
        role="alert"
        data-testid="operating-mode-status"
        className="inline-flex items-center gap-1 rounded-md border border-amber-300 px-2 py-1 text-xs font-medium text-amber-800 dark:border-amber-700 dark:text-amber-300"
      >
        Operating mode unknown (API unreachable)
      </span>
    );
  }

  return (
    <span
      data-testid="operating-mode-status"
      data-mode={data.mode}
      className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
    >
      Mode: {MODE_LABEL[data.mode] ?? data.mode}
    </span>
  );
}
