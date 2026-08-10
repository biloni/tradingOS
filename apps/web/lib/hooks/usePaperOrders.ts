import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelOrder,
  confirmOrder,
  createOrder,
  listOrders,
  type CreateOrderInput,
} from "@/lib/api/paperOrders";

export function useOrders(accountId: string | undefined) {
  return useQuery({
    queryKey: ["orders", accountId],
    queryFn: () => listOrders(accountId as string),
    enabled: Boolean(accountId),
  });
}

/** A confirm/cancel/create can change both the order and the derived
 * portfolio (cash/positions), so every mutation here invalidates both
 * domains rather than just its own — avoids showing stale cash/position
 * figures right after an action that just changed them. */
function useInvalidateOrdersAndPortfolio(accountId: string | undefined) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["orders", accountId] });
    void queryClient.invalidateQueries({ queryKey: ["portfolio", "accounts", accountId] });
  };
}

export function useCreateOrder(accountId: string | undefined) {
  const invalidate = useInvalidateOrdersAndPortfolio(accountId);
  return useMutation({
    mutationFn: (input: CreateOrderInput) => createOrder(input),
    onSuccess: invalidate,
  });
}

export function useConfirmOrder(accountId: string | undefined) {
  const invalidate = useInvalidateOrdersAndPortfolio(accountId);
  return useMutation({
    mutationFn: (id: string) => confirmOrder(id),
    onSuccess: invalidate,
  });
}

export function useCancelOrder(accountId: string | undefined) {
  const invalidate = useInvalidateOrdersAndPortfolio(accountId);
  return useMutation({
    mutationFn: (id: string) => cancelOrder(id),
    onSuccess: invalidate,
  });
}
