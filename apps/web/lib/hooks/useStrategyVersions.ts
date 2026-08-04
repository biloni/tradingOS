import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveStrategyVersion,
  compareStrategyVersion,
  getStrategyVersion,
  listStrategyVersions,
  proposeStrategyVersion,
  rejectStrategyVersion,
  type ApproveStrategyVersionInput,
  type RejectStrategyVersionInput,
  type StrategyBacktestParams,
} from "@/lib/api/strategyVersions";

export function useStrategyVersions() {
  return useQuery({ queryKey: ["strategy-versions"], queryFn: listStrategyVersions });
}

export function useStrategyVersion(id: number) {
  return useQuery({
    queryKey: ["strategy-versions", id],
    queryFn: () => getStrategyVersion(id),
    enabled: Number.isFinite(id),
  });
}

export function useProposeStrategyVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: proposeStrategyVersion,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["strategy-versions"] });
    },
  });
}

/** Read-only and repeatable (ADR-028) — no invalidation needed beyond
 * backtests, since compare never changes a StrategyVersion's status. */
export function useCompareStrategyVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, params }: { id: number; params: StrategyBacktestParams }) =>
      compareStrategyVersion(id, params),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });
}

export function useApproveStrategyVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: ApproveStrategyVersionInput }) =>
      approveStrategyVersion(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["strategy-versions"] });
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });
}

export function useRejectStrategyVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: RejectStrategyVersionInput }) =>
      rejectStrategyVersion(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["strategy-versions"] });
    },
  });
}
