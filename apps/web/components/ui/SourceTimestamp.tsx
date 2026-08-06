import type { FreshnessStatus } from "./DataFreshnessBadge";

const FRESHNESS_TEXT: Record<FreshnessStatus, string> = {
  FRESH: "",
  STALE: " (stale)",
  UNAVAILABLE: " (unavailable)",
};

/**
 * Principle 3: every market fact carries source, timestamp, timezone,
 * and freshness. This is the smallest reusable rendering of that
 * envelope for inline use (e.g. under an evidence item or a plan
 * banner) — always plain text, so it reads correctly with a screen
 * reader or in a color-blind-unfriendly environment without any change.
 */
export function SourceTimestamp({
  source,
  timestamp,
  freshness = "FRESH",
}: {
  source: string;
  timestamp: string;
  freshness?: FreshnessStatus;
}) {
  return (
    <span className="text-xs text-zinc-500 dark:text-zinc-400">
      {source} &middot; as of {timestamp}
      {FRESHNESS_TEXT[freshness]}
    </span>
  );
}
