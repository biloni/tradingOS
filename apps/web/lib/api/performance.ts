import { apiGet } from "./client";

export type Drawdown = {
  max_drawdown_pct: string;
  peak_index: number | null;
  trough_index: number | null;
  recovery_index: number | null;
  recovery_periods: number | null;
};

/**
 * Only the fields the portfolio strip (Revision Prompt 15) actually
 * displays are typed here — the real response carries many more
 * (Sharpe/Sortino/beta/alpha/etc., see docs/API_CONTRACTS.md area 25) —
 * intentionally a subset, not a re-declaration of the whole contract.
 */
export type PortfolioPerformanceSummary = {
  as_of: string;
  equity: string | null;
  cash: string | null;
  daily_return_pct: string | null;
  weekly_return_pct: string | null;
  realized_pnl: string;
  unrealized_pnl: string;
  drawdown: Drawdown;
  gross_exposure_pct: string | null;
  sample_size_days: number;
};

export function getPortfolioPerformance(accountId: string): Promise<PortfolioPerformanceSummary> {
  return apiGet<PortfolioPerformanceSummary>(`/api/v1/performance/portfolio/${accountId}`);
}
