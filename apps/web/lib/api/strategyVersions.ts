import { apiGet, apiPost } from "./client";
import type { BacktestRun } from "./backtests";

export type StrategyVersionStatus = "PROPOSED" | "ACTIVE" | "REJECTED" | "SUPERSEDED";

export type StrategyVersion = {
  id: number;
  name: string;
  config: Record<string, unknown>;
  status: StrategyVersionStatus;
  decided_at: string | null;
  decision_comment: string | null;
  created_at: string;
};

export type StrategyConfigInput = {
  weights: {
    trend: number;
    momentum: number;
    macd: number;
    bollinger: number;
  };
  rsi_bullish_low: number;
  rsi_bullish_high: number;
  rsi_oversold: number;
};

export type ProposeStrategyVersionInput = {
  name: string;
  config: StrategyConfigInput;
};

/** Same optional overrides as backtests.RunBacktestInput, minus
 * strategy_version_id (the path param already picks the candidate) —
 * applied identically to both sides of a comparison. */
export type StrategyBacktestParams = {
  date_range_start?: string | null;
  date_range_end?: string | null;
  entry_score_threshold?: string;
  exit_score_threshold?: string;
  max_holding_days?: number;
  position_size_pct?: string;
  starting_cash?: string;
  benchmark_ticker?: string | null;
};

export type ApproveStrategyVersionInput = StrategyBacktestParams & {
  comment?: string | null;
};

export type RejectStrategyVersionInput = {
  comment?: string | null;
};

export type ComparisonDelta = {
  total_return_pct: string;
  max_drawdown_pct: string;
  win_rate_pct: string;
  avg_win_pct: string;
  avg_loss_pct: string;
  num_trades: number;
};

export type StrategyComparison = {
  candidate_backtest: BacktestRun;
  active_backtest: BacktestRun;
  delta: ComparisonDelta;
};

export function proposeStrategyVersion(
  input: ProposeStrategyVersionInput,
): Promise<StrategyVersion> {
  return apiPost<StrategyVersion>("/api/v1/strategy-versions", input);
}

export function listStrategyVersions(): Promise<StrategyVersion[]> {
  return apiGet<StrategyVersion[]>("/api/v1/strategy-versions");
}

export function getStrategyVersion(id: number): Promise<StrategyVersion> {
  return apiGet<StrategyVersion>(`/api/v1/strategy-versions/${id}`);
}

export function compareStrategyVersion(
  id: number,
  params: StrategyBacktestParams,
): Promise<StrategyComparison> {
  return apiPost<StrategyComparison>(`/api/v1/strategy-versions/${id}/compare`, params);
}

export function approveStrategyVersion(
  id: number,
  input: ApproveStrategyVersionInput,
): Promise<StrategyVersion> {
  return apiPost<StrategyVersion>(`/api/v1/strategy-versions/${id}/approve`, input);
}

export function rejectStrategyVersion(
  id: number,
  input: RejectStrategyVersionInput,
): Promise<StrategyVersion> {
  return apiPost<StrategyVersion>(`/api/v1/strategy-versions/${id}/reject`, input);
}
