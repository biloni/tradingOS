import { useQuery } from "@tanstack/react-query";
import { getPortfolio, getReconciliation } from "@/lib/api/portfolio";

export function usePortfolio() {
  return useQuery({ queryKey: ["portfolio"], queryFn: getPortfolio });
}

export function useReconciliation() {
  return useQuery({ queryKey: ["portfolio", "reconciliation"], queryFn: getReconciliation });
}
