import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelOrder,
  confirmOrder,
  getOrder,
  listOrders,
  proposeOrder,
  refreshOrder,
} from "@/lib/api/paperOrders";

export function usePaperOrders() {
  return useQuery({ queryKey: ["paper-orders"], queryFn: listOrders });
}

export function usePaperOrder(id: number) {
  return useQuery({
    queryKey: ["paper-orders", id],
    queryFn: () => getOrder(id),
    enabled: Number.isFinite(id),
  });
}

/** A confirm/cancel/refresh can change both the order and the derived
 * portfolio (cash/positions), so every mutation here invalidates both
 * domains rather than just its own — avoids showing stale cash/position
 * figures right after an action that just changed them. */
function useInvalidateOrdersAndPortfolio() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["paper-orders"] });
    void queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };
}

export function useProposeOrder() {
  const invalidate = useInvalidateOrdersAndPortfolio();
  return useMutation({
    mutationFn: proposeOrder,
    onSuccess: invalidate,
  });
}

export function useConfirmOrder() {
  const invalidate = useInvalidateOrdersAndPortfolio();
  return useMutation({
    mutationFn: confirmOrder,
    onSuccess: invalidate,
  });
}

export function useRefreshOrder() {
  const invalidate = useInvalidateOrdersAndPortfolio();
  return useMutation({
    mutationFn: refreshOrder,
    onSuccess: invalidate,
  });
}

export function useCancelOrder() {
  const invalidate = useInvalidateOrdersAndPortfolio();
  return useMutation({
    mutationFn: cancelOrder,
    onSuccess: invalidate,
  });
}
