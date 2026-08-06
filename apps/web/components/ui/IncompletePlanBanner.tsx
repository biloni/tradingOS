/**
 * docs/MORNING_PLAN_SPEC.md's MDS-4: publish INCOMPLETE rather than
 * fabricate certainty. `role="alert"` since this is the one banner that
 * should interrupt a screen reader user's flow — it changes how the
 * whole page's contents should be trusted.
 */
export function IncompletePlanBanner({ reasons = [] }: { reasons?: string[] }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
    >
      <div className="flex items-center gap-2 font-medium">
        <span aria-hidden="true">&#9888;</span>
        This plan is INCOMPLETE
      </div>
      {reasons.length > 0 && (
        <ul className="mt-1 list-inside list-disc text-xs opacity-90">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
