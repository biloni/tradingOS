import { useQuery } from "@tanstack/react-query";
import { getBars, getIndicators, getSymbols } from "@/lib/api/symbols";

export function useSymbols() {
  return useQuery({ queryKey: ["symbols"], queryFn: getSymbols });
}

export function useBars(ticker: string, params?: { start?: string; end?: string }) {
  return useQuery({
    queryKey: ["symbols", ticker, "bars", params ?? {}],
    queryFn: () => getBars(ticker, params),
    enabled: Boolean(ticker),
  });
}

export function useIndicators(ticker: string, asOf?: string) {
  return useQuery({
    queryKey: ["symbols", ticker, "indicators", asOf ?? null],
    queryFn: () => getIndicators(ticker, asOf),
    enabled: Boolean(ticker),
  });
}
