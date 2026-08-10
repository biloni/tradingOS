import { useQuery } from "@tanstack/react-query";
import { getBars, getIndicators, getSymbols } from "@/lib/api/symbols";

export function useSymbols() {
  return useQuery({ queryKey: ["symbols"], queryFn: getSymbols });
}

export function useBars(ticker: string, params?: { limit?: number }) {
  return useQuery({
    queryKey: ["symbols", ticker, "bars", params ?? {}],
    queryFn: () => getBars(ticker, params),
    enabled: Boolean(ticker),
  });
}

export function useIndicators(ticker: string) {
  return useQuery({
    queryKey: ["symbols", ticker, "indicators"],
    queryFn: () => getIndicators(ticker),
    enabled: Boolean(ticker),
  });
}
