import { apiGet } from "./client";

/**
 * Previously called a nonexistent `/api/v1/symbols*` prefix (404s
 * discovered live while verifying Revision Prompt 15's dashboard work —
 * the real routers are `/api/v1/instruments` for the symbol list and
 * `/api/v1/market/instruments/{ticker}/*` for bars/indicators,
 * docs/API_CONTRACTS.md area 3). Type/field names kept identical to
 * before so the consuming pages (`app/symbols/**`) don't need changes.
 */
export type Symbol = {
  id: string;
  ticker: string;
  name: string;
  exchange: string;
  asset_type: string;
  active: boolean;
};

export type PriceBar = {
  as_of: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
};

export type IndicatorPoint = {
  as_of: string;
  indicator_name: string;
  value: string;
};

export async function getSymbols(): Promise<Symbol[]> {
  const page = await apiGet<{ items: Symbol[] }>("/api/v1/instruments?limit=200");
  return page.items;
}

export function getBars(ticker: string, params?: { limit?: number }): Promise<PriceBar[]> {
  const qs = params?.limit ? `?limit=${params.limit}` : "";
  return apiGet<PriceBar[]>(`/api/v1/market/instruments/${ticker}/bars${qs}`);
}

export function getIndicators(ticker: string): Promise<IndicatorPoint[]> {
  return apiGet<IndicatorPoint[]>(`/api/v1/market/instruments/${ticker}/indicators`);
}
