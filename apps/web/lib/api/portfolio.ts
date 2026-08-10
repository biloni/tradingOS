import { apiGet } from "./client";

/**
 * This module previously called `/api/v1/portfolio` and
 * `/api/v1/portfolio/reconciliation` — neither exists on the current
 * backend (404s discovered live while verifying Revision Prompt 15's
 * dashboard work). Rewired to the real Revision Prompt 8 endpoints
 * under `/api/v1/portfolio/accounts/*`.
 */
export type Instrument = {
  id: string;
  ticker: string;
  name: string;
  exchange: string;
  asset_type: string;
  active: boolean;
};

export type Position = {
  instrument: Instrument;
  quantity: string;
  avg_cost: string;
  market_value: string | null;
};

export type CashSummary = {
  account_id: string;
  cash: string;
  starting_cash: string;
};

export type RiskSnapshot = {
  as_of: string;
  gross_exposure_pct: string | null;
  largest_position_pct: string | null;
  sector_concentration: Record<string, unknown> | null;
  correlation_flag: boolean;
};

export type AccountDetail = {
  account: { id: string; account_type: string; name: string; base_currency: string; is_active: boolean };
  cash: CashSummary;
  positions: Position[];
  latest_risk_snapshot: RiskSnapshot | null;
};

export function getAccountDetail(accountId: string): Promise<AccountDetail> {
  return apiGet<AccountDetail>(`/api/v1/portfolio/accounts/${accountId}`);
}

export type ReconciliationLine = {
  instrument: Instrument;
  internal_quantity: string;
  broker_reported_quantity: string | null;
  status: string;
  discrepancy_detail: string | null;
};

export type ReconciliationRun = {
  id: string;
  as_of: string;
  overall_status: string;
  lines: ReconciliationLine[];
};

/**
 * The most recent reconciliation run, if one has ever been triggered
 * (`POST /accounts/{id}/reconcile`) — there is no "live diff against the
 * broker right now" endpoint; reconciliation is always a discrete,
 * timestamped run, never an implicit background computation.
 */
export function listReconciliationRuns(accountId: string): Promise<ReconciliationRun[]> {
  return apiGet<ReconciliationRun[]>(`/api/v1/portfolio/accounts/${accountId}/reconciliation-runs`);
}
