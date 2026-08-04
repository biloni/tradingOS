import { apiGet } from "./client";

export type Position = {
  ticker: string;
  quantity: number;
  avg_entry_price: string;
  current_price: string | null;
  market_value: string | null;
  unrealized_pl: string | null;
};

export type PortfolioSnapshot = {
  cash_usd: string;
  positions: Position[];
  total_market_value: string;
  total_equity: string;
};

export type ReconciliationRow = {
  ticker: string;
  our_quantity: number;
  alpaca_quantity: string;
  discrepancy: string;
};

export function getPortfolio(): Promise<PortfolioSnapshot> {
  return apiGet<PortfolioSnapshot>("/api/v1/portfolio");
}

export function getReconciliation(): Promise<ReconciliationRow[]> {
  return apiGet<ReconciliationRow[]>("/api/v1/portfolio/reconciliation");
}
