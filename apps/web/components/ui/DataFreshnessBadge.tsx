export type FreshnessStatus = "FRESH" | "STALE" | "UNAVAILABLE";

const FRESHNESS_COPY: Record<FreshnessStatus, { label: string; icon: string; classes: string }> = {
  FRESH: {
    label: "Fresh",
    icon: "✓",
    classes: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  STALE: {
    label: "Stale",
    icon: "!",
    classes: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
  UNAVAILABLE: {
    label: "Unavailable",
    icon: "✕",
    classes: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  },
};

/**
 * Principle 3/5 (every fact carries freshness; missing/stale data is
 * shown explicitly, never silently substituted). The word ("Fresh"/
 * "Stale"/"Unavailable") is the primary signal — the icon and color are
 * reinforcement, never the only cue (accessibility requirement).
 */
export function DataFreshnessBadge({
  status,
  asOf,
}: {
  status: FreshnessStatus;
  asOf?: string;
}) {
  const copy = FRESHNESS_COPY[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${copy.classes}`}
      title={asOf ? `As of ${asOf}` : undefined}
    >
      <span aria-hidden="true">{copy.icon}</span>
      {copy.label}
      {asOf ? <span className="font-normal opacity-80">&middot; {asOf}</span> : null}
    </span>
  );
}
