import { BacktestReport } from "@/components/backtests/BacktestReport";
import type { StrategyComparison } from "@/lib/api/strategyVersions";

function DeltaMetric({
  label,
  value,
  positiveIsGood = true,
}: {
  label: string;
  value: string;
  positiveIsGood?: boolean;
}) {
  const numeric = Number(value.replace(/%$/, ""));
  const good = positiveIsGood ? numeric >= 0 : numeric <= 0;
  return (
    <div>
      <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">{label}</div>
      <div
        className={`text-lg font-semibold ${good ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
      >
        {numeric >= 0 ? "+" : ""}
        {value}
      </div>
    </div>
  );
}

/** Read-only, repeatable (ADR-028) — never used to auto-decide anything;
 * surfaced for a human to read before an explicit approve/reject. */
export function CompareView({ comparison }: { comparison: StrategyComparison }) {
  const { candidate_backtest, active_backtest, delta } = comparison;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h3 className="mb-3 text-base font-medium text-black dark:text-zinc-50">
          Delta (candidate &minus; active)
        </h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <DeltaMetric label="Total return" value={`${delta.total_return_pct}%`} />
          <DeltaMetric
            label="Max drawdown"
            value={`${delta.max_drawdown_pct}%`}
            positiveIsGood={false}
          />
          <DeltaMetric label="Win rate" value={`${delta.win_rate_pct}%`} />
          <DeltaMetric label="Avg win" value={`${delta.avg_win_pct}%`} />
          <DeltaMetric label="Avg loss" value={`${delta.avg_loss_pct}%`} positiveIsGood={false} />
          <DeltaMetric label="Trades" value={String(delta.num_trades)} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <BacktestReport run={candidate_backtest} title="Candidate" />
        <BacktestReport run={active_backtest} title="Active" />
      </div>
    </div>
  );
}
