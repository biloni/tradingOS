import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { StatusPill } from "@/components/ui/StatusPill";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import type { BacktestRun } from "@/lib/api/backtests";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">{label}</div>
      <div className="text-lg font-semibold text-black dark:text-zinc-50">{value}</div>
    </div>
  );
}

function pct(value: string): string {
  return `${Number(value).toFixed(2)}%`;
}

function usd(value: string): string {
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** Reused by both backtests/[id] and the strategy compare view (two of
 * these side by side) — one place for the equity-curve chart + trade-log
 * table + summary metrics. */
export function BacktestReport({ run, title }: { run: BacktestRun; title?: string }) {
  const rs = run.results_summary;

  return (
    <div className="flex flex-col gap-4">
      {title && <h3 className="text-base font-medium text-black dark:text-zinc-50">{title}</h3>}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Metric label="Ending equity" value={usd(rs.ending_equity)} />
        <Metric label="Total return" value={pct(rs.total_return_pct)} />
        <Metric label="Max drawdown" value={pct(rs.max_drawdown_pct)} />
        <Metric label="Win rate" value={pct(rs.win_rate_pct)} />
        <Metric label="Trades" value={String(rs.num_trades)} />
        <Metric label="Avg win" value={pct(rs.avg_win_pct)} />
        <Metric label="Avg loss" value={pct(rs.avg_loss_pct)} />
        <Metric
          label="Benchmark return"
          value={rs.benchmark_return_pct !== null ? pct(rs.benchmark_return_pct) : "—"}
        />
      </div>

      <div>
        <h4 className="mb-2 text-sm font-medium text-zinc-600 dark:text-zinc-400">
          Equity curve
        </h4>
        {rs.equity_curve.length > 0 ? (
          <EquityCurveChart points={rs.equity_curve} />
        ) : (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No equity curve data.</p>
        )}
      </div>

      <div>
        <h4 className="mb-2 text-sm font-medium text-zinc-600 dark:text-zinc-400">
          Trade log ({rs.trades.length})
        </h4>
        {rs.trades.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No trades in this run.</p>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>Ticker</Th>
                <Th>Entry</Th>
                <Th>Exit</Th>
                <Th>Qty</Th>
                <Th>P&amp;L</Th>
                <Th>Reason</Th>
              </Tr>
            </Thead>
            <Tbody>
              {rs.trades.map((trade, index) => (
                <Tr key={index}>
                  <Td className="font-medium">{trade.ticker}</Td>
                  <Td>
                    {trade.entry_date} @ ${Number(trade.entry_price).toFixed(2)}
                  </Td>
                  <Td>
                    {trade.exit_date} @ ${Number(trade.exit_price).toFixed(2)}
                  </Td>
                  <Td>{trade.quantity}</Td>
                  <Td
                    className={
                      Number(trade.pnl_usd) < 0
                        ? "text-red-600 dark:text-red-400"
                        : "text-emerald-600 dark:text-emerald-400"
                    }
                  >
                    ${Number(trade.pnl_usd).toFixed(2)} ({Number(trade.pnl_pct).toFixed(2)}%)
                  </Td>
                  <Td>
                    <StatusPill status={trade.exit_reason} />
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </div>
    </div>
  );
}
