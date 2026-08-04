import { apiGet, apiPost } from "./client";

export type Trade = {
  ticker: string;
  entry_date: string;
  entry_price: string;
  exit_date: string;
  exit_price: string;
  quantity: number;
  pnl_usd: string;
  pnl_pct: string;
  exit_reason: "SIGNAL_EXIT" | "MAX_HOLDING_DAYS" | "END_OF_BACKTEST";
};

export type EquityPoint = {
  as_of: string;
  equity: string;
};

export type ResultsSummary = {
  ending_equity: string;
  total_return_pct: string;
  max_drawdown_pct: string;
  win_rate_pct: string;
  num_trades: number;
  avg_win_pct: string;
  avg_loss_pct: string;
  benchmark_return_pct: string | null;
  equity_curve: EquityPoint[];
  trades: Trade[];
};

export type BacktestParameters = {
  entry_score_threshold: string;
  exit_score_threshold: string;
  max_holding_days: number;
  position_size_pct: string;
  starting_cash: string;
  benchmark_ticker: string | null;
};

export type BacktestRun = {
  id: number;
  strategy_version_id: number;
  date_range_start: string;
  date_range_end: string;
  parameters: BacktestParameters;
  results_summary: ResultsSummary;
  created_at: string;
};

export type RunBacktestInput = {
  date_range_start?: string | null;
  date_range_end?: string | null;
  strategy_version_id?: number | null;
  entry_score_threshold?: string;
  exit_score_threshold?: string;
  max_holding_days?: number;
  position_size_pct?: string;
  starting_cash?: string;
  benchmark_ticker?: string | null;
};

export function runBacktest(input: RunBacktestInput): Promise<BacktestRun> {
  return apiPost<BacktestRun>("/api/v1/backtests", input);
}

export function listBacktests(): Promise<BacktestRun[]> {
  return apiGet<BacktestRun[]>("/api/v1/backtests");
}

export function getBacktest(id: number): Promise<BacktestRun> {
  return apiGet<BacktestRun>(`/api/v1/backtests/${id}`);
}
