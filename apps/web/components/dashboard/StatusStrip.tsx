import type { TopStatus } from "@/lib/api/morningPlan";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/StatusPill";

function formatCountdown(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds <= 0) return "Market open";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m to open` : `${m}m to open`;
}

/**
 * Revision Prompt 15's "Status strip": market date, countdown, plan
 * state, freshness, regime, operating mode, kill switch — one row, no
 * casino imagery or urgency manipulation. Every value comes straight
 * from `TopStatusResponse` (the same object the dashboard's read API
 * already computes as one unit), never re-derived here.
 */
export function StatusStrip({ status }: { status: TopStatus }) {
  const evidenceCutoff = status.evidence_cutoff
    ? new Date(status.evidence_cutoff)
    : null;

  return (
    <Card
      role="region"
      aria-label="Status"
      className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm"
    >
      <div className="font-medium text-black dark:text-zinc-50">
        {status.market_date}
        {!status.is_trading_day && (
          <span className="ml-2 text-xs font-normal text-zinc-500 dark:text-zinc-400">
            (not a trading day{status.market_closed_reason ? `: ${status.market_closed_reason}` : ""})
          </span>
        )}
      </div>

      <span className="text-zinc-600 dark:text-zinc-400">
        {formatCountdown(status.countdown_to_open_seconds)}
      </span>

      <span className="flex items-center gap-1.5">
        <span className="text-zinc-500 dark:text-zinc-400">Plan:</span>
        <StatusPill status={status.plan_status} />
        {status.plan_version_label && (
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            ({status.plan_version_label})
          </span>
        )}
      </span>

      <span className="flex items-center gap-1.5 text-zinc-600 dark:text-zinc-400">
        Evidence cutoff:{" "}
        {evidenceCutoff ? (
          <time dateTime={status.evidence_cutoff ?? undefined} title={status.evidence_cutoff ?? undefined}>
            {evidenceCutoff.toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </time>
        ) : (
          "unavailable"
        )}
      </span>

      {status.regime_classification && (
        <span className="flex items-center gap-1.5">
          <span className="text-zinc-500 dark:text-zinc-400">Regime:</span>
          <StatusPill status={status.regime_classification} />
        </span>
      )}

      <span className="flex items-center gap-1.5">
        <span className="text-zinc-500 dark:text-zinc-400">Mode:</span>
        <StatusPill status={status.operating_mode} />
      </span>

      <span className="flex items-center gap-1.5">
        <span className="text-zinc-500 dark:text-zinc-400">Broker:</span>
        <StatusPill status={status.provider_broker_status} />
      </span>

      <span
        data-testid="kill-switch-indicator"
        role={status.kill_switch_active ? "alert" : undefined}
        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
          status.kill_switch_active
            ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
            : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
        }`}
      >
        <span aria-hidden="true">{status.kill_switch_active ? "⛔" : "○"}</span>
        Kill switch {status.kill_switch_active ? "ACTIVE" : "off"}
      </span>
    </Card>
  );
}
