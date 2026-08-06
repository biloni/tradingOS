export type OrderTimelineStepStatus = "done" | "current" | "pending" | "invalidated";

export type OrderTimelineStep = {
  label: string;
  status: OrderTimelineStepStatus;
};

const STEP_ICON: Record<OrderTimelineStepStatus, string> = {
  done: "✓",
  current: "●",
  pending: "○",
  invalidated: "✕",
};

const STEP_CLASSES: Record<OrderTimelineStepStatus, string> = {
  done: "border-emerald-500 bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  current: "border-blue-500 bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  pending: "border-zinc-300 bg-zinc-100 text-zinc-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400",
  invalidated: "border-red-500 bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

/**
 * docs/ORDER_AUTHORITY_MODEL.md's lifecycle diagram, rendered as a
 * horizontal (desktop) / vertical (mobile, via flex-wrap) step list.
 * Each step's status is conveyed by its icon + text label, not color
 * alone — a screen reader announces "Approved, done" the same way a
 * sighted user reads the checkmark.
 */
export function OrderStateTimeline({ steps }: { steps: OrderTimelineStep[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-2" aria-label="Order lifecycle">
      {steps.map((step, index) => (
        <li key={step.label} className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${STEP_CLASSES[step.status]}`}
          >
            <span aria-hidden="true">{STEP_ICON[step.status]}</span>
            {step.label}
            <span className="sr-only"> ({step.status})</span>
          </span>
          {index < steps.length - 1 && (
            <span aria-hidden="true" className="text-zinc-300 dark:text-zinc-700">
              &rarr;
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
