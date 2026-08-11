import { useQuery } from "@tanstack/react-query";
import { getCostBudgetStatus, getMetrics, getSchedulerStatus, listJobRuns } from "@/lib/api/ops";

/**
 * Revision Prompt 16 — the job dashboard / metrics page polls both on
 * a short interval since this is operational, "what's happening right
 * now" data, unlike the mostly-static reference data elsewhere in this
 * app that only needs `staleTime`.
 */
export function useMetrics() {
  return useQuery({
    queryKey: ["ops", "metrics"],
    queryFn: getMetrics,
    refetchInterval: 15_000,
  });
}

export function useJobRuns(limit = 20) {
  return useQuery({
    queryKey: ["ops", "job-runs", limit],
    queryFn: () => listJobRuns(limit),
    refetchInterval: 15_000,
  });
}

export function useCostBudgetStatus() {
  return useQuery({
    queryKey: ["ops", "cost-budget"],
    queryFn: getCostBudgetStatus,
    refetchInterval: 15_000,
  });
}

export function useSchedulerStatus() {
  return useQuery({
    queryKey: ["ops", "scheduler"],
    queryFn: getSchedulerStatus,
    refetchInterval: 15_000,
  });
}
