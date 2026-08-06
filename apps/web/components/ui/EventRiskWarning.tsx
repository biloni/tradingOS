/**
 * docs/HYBRID_EARNINGS_STRATEGY.md's gap-risk requirement (HES-5): a
 * stop is never represented as a guarantee. Rendered as a labeled
 * warning banner (role="alert"-adjacent, "status" since it's not an
 * error), always with explicit text, never a color-only indicator.
 */
export function EventRiskWarning({
  eventLabel,
  detail,
}: {
  eventLabel: string;
  detail?: string;
}) {
  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <span aria-hidden="true" className="mt-0.5">
        &#9888;
      </span>
      <div>
        <div className="font-medium">Event risk: {eventLabel}</div>
        <div className="text-xs opacity-90">
          {detail ??
            "A stop order is not a guarantee of the stop price — overnight/event gaps can execute well beyond it."}
        </div>
      </div>
    </div>
  );
}
