import type { TopStatus } from "@/lib/api/morningPlan";
import type { PortfolioPerformanceSummary } from "@/lib/api/performance";
import { Card } from "@/components/ui/Card";

function formatUsd(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatPct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

/**
 * "Never rely on green/red color alone" (Revision Prompt 15) — every
 * signed figure below carries an explicit +/- prefix in the text itself,
 * so the sign reads correctly even with color perception removed; the
 * `pct-positive`/`pct-negative` classes are a secondary reinforcement,
 * not the only cue.
 */
function SignedStat({ label, value }: { label: string; value: string }) {
  const isNegative = value.startsWith("-");
  return (
    <div className="flex flex-col">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">{label}</span>
      <span
        className={`font-medium ${
          isNegative
            ? "text-red-700 dark:text-red-400"
            : value.startsWith("+")
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-black dark:text-zinc-50"
        }`}
      >
        {value}
      </span>
    </div>
  );
}

/**
 * Revision Prompt 15's "Portfolio strip": equity, cash, daily/weekly
 * P&L, drawdown, exposure, risk remaining. Equity/cash/exposure/risk
 * budget come from `TopStatusResponse` (the same object every other
 * dashboard figure ties out against); daily/weekly return and drawdown
 * come from `GET /api/v1/performance/portfolio/{account}` — Revision
 * Prompt 12's own shared statistics library, never re-derived here.
 * `performance` is `undefined` while that second call is loading/absent
 * (e.g. no account yet) — the strip still renders the fields it has.
 */
export function PortfolioStrip({
  status,
  performance,
}: {
  status: TopStatus;
  performance: PortfolioPerformanceSummary | undefined;
}) {
  const riskRemainingPct =
    status.risk_budget_pct !== null
      ? (100 - Number(status.risk_budget_pct)).toFixed(1)
      : null;

  return (
    <Card role="region" aria-label="Portfolio" className="flex flex-wrap gap-x-6 gap-y-3 text-sm">
      <div className="flex flex-col">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Equity</span>
        <span className="font-medium text-black dark:text-zinc-50">
          {formatUsd(status.total_equity)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Cash</span>
        <span className="font-medium text-black dark:text-zinc-50">{formatUsd(status.cash)}</span>
      </div>
      <SignedStat label="Day P&amp;L" value={formatPct(performance?.daily_return_pct)} />
      <SignedStat label="Week P&amp;L" value={formatPct(performance?.weekly_return_pct)} />
      <div className="flex flex-col">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Max drawdown</span>
        <span className="font-medium text-black dark:text-zinc-50">
          {performance ? formatPct(performance.drawdown.max_drawdown_pct) : "—"}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Exposure</span>
        <span className="font-medium text-black dark:text-zinc-50">
          {formatPct(status.exposure_pct)}
        </span>
      </div>
      <div className="flex flex-col">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Risk budget used / remaining</span>
        <span className="font-medium text-black dark:text-zinc-50">
          {status.risk_budget_pct !== null
            ? `${formatPct(status.risk_budget_pct)} used, ${riskRemainingPct}% remaining`
            : "—"}
        </span>
      </div>
    </Card>
  );
}
