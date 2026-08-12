import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveOrderApproval,
  getOrderApproval,
  listOrderApprovals,
  refreshOrderApproval,
  rejectOrderApproval,
  submitOrderApproval,
} from "@/lib/api/orderApprovals";
import type { OrderApprovalStatus, OrderSubmitResult } from "@/lib/api/orderApprovals";

export function useOrderApproval(id: string | undefined) {
  return useQuery({
    queryKey: ["order-approvals", id],
    queryFn: () => getOrderApproval(id as string),
    enabled: Boolean(id),
  });
}

/** The approval queue (`/approvals`) — defaults to `PENDING`, polled like
 * the rest of this app's operational views. */
export function useOrderApprovals(status?: OrderApprovalStatus) {
  return useQuery({
    queryKey: ["order-approvals", "list", status ?? "PENDING"],
    queryFn: () => listOrderApprovals(status),
    refetchInterval: 15_000,
  });
}

/** ORDER FLOW steps 2-4 preview — read-only, safe to refetch on demand
 * (e.g. a "Refresh" button) without any invalidation side effect. */
export function useRefreshOrderApproval(id: string | undefined) {
  return useQuery({
    queryKey: ["order-approvals", id, "refresh"],
    queryFn: () => refreshOrderApproval(id as string),
    enabled: Boolean(id),
    staleTime: 0,
  });
}

export function useApproveOrderApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, approvedBy }: { id: string; approvedBy: string }) =>
      approveOrderApproval(id, approvedBy),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["order-approvals", variables.id] });
    },
  });
}

export function useRejectOrderApproval() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => rejectOrderApproval(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["order-approvals", id] });
    },
  });
}

export function useSubmitOrderApproval() {
  const queryClient = useQueryClient();
  return useMutation<
    OrderSubmitResult,
    Error,
    { id: string; input: Parameters<typeof submitOrderApproval>[1] }
  >({
    mutationFn: ({ id, input }) => submitOrderApproval(id, input),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["order-approvals", variables.id] });
      void queryClient.invalidateQueries({ queryKey: ["morning-plan", "dashboard"] });
    },
  });
}
