import { apiGet } from "./client";

export type Symbol = {
  id: number;
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
  source: string;
  adjustment: string;
  fetched_at: string;
};

export type IndicatorPoint = {
  as_of: string;
  indicator_name: string;
  version: string;
  value: string;
  computed_at: string;
};

export function getSymbols(): Promise<Symbol[]> {
  return apiGet<Symbol[]>("/api/v1/symbols");
}

export function getBars(
  ticker: string,
  params?: { start?: string; end?: string },
): Promise<PriceBar[]> {
  const query = new URLSearchParams();
  if (params?.start) query.set("start", params.start);
  if (params?.end) query.set("end", params.end);
  const qs = query.toString();
  return apiGet<PriceBar[]>(`/api/v1/symbols/${ticker}/bars${qs ? `?${qs}` : ""}`);
}

export function getIndicators(ticker: string, asOf?: string): Promise<IndicatorPoint[]> {
  const qs = asOf ? `?as_of=${asOf}` : "";
  return apiGet<IndicatorPoint[]>(`/api/v1/symbols/${ticker}/indicators${qs}`);
}
