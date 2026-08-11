type Tone = "neutral" | "positive" | "warning" | "negative" | "info";

/** Covers every status/enum string this app renders: PaperOrderStatus,
 * StrategyVersionStatus, RecommendationConfidence bands, and backtest
 * trade exit reasons — one shared lookup rather than a per-domain pill. */
const STATUS_TONES: Record<string, Tone> = {
  DRAFT: "neutral",
  SUBMITTED: "info",
  PARTIALLY_FILLED: "warning",
  FILLED: "positive",
  CANCELED: "neutral",
  REJECTED: "negative",
  PROPOSED: "info",
  ACTIVE: "positive",
  SUPERSEDED: "neutral",
  LOW: "warning",
  MEDIUM: "info",
  HIGH: "positive",
  SIGNAL_EXIT: "info",
  MAX_HOLDING_DAYS: "warning",
  END_OF_BACKTEST: "neutral",
  RUNNING: "info",
  COMPLETED: "positive",
  FAILED: "negative",
};

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  positive: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  negative: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  info: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
};

export function StatusPill({ status }: { status: string }) {
  const tone = STATUS_TONES[status] ?? "neutral";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
