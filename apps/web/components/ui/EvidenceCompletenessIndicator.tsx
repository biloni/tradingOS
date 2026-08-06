/**
 * docs/MORNING_PLAN_SPEC.md's "what data is required before COMPLETE"
 * section: shows exactly which evidence categories a recommendation had
 * available, as text ("4 of 5 evidence categories available"), not a
 * bare progress bar color alone.
 */
export function EvidenceCompletenessIndicator({
  available,
  total,
  missingCategories = [],
}: {
  available: number;
  total: number;
  missingCategories?: string[];
}) {
  const complete = available >= total;
  return (
    <div
      role="status"
      className="inline-flex flex-col gap-0.5 text-xs"
      aria-label={`${available} of ${total} evidence categories available`}
    >
      <span
        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${
          complete
            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
            : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        }`}
      >
        <span aria-hidden="true">{complete ? "✓" : "!"}</span>
        {available} of {total} evidence categories available
      </span>
      {!complete && missingCategories.length > 0 && (
        <span className="text-zinc-500 dark:text-zinc-400">
          Missing: {missingCategories.join(", ")}
        </span>
      )}
    </div>
  );
}
