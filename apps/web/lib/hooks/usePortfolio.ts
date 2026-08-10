import { useQuery } from "@tanstack/react-query";
import { getAccountDetail, listReconciliationRuns } from "@/lib/api/portfolio";

export function useAccountDetail(accountId: string | undefined) {
  return useQuery({
    queryKey: ["portfolio", "accounts", accountId],
    queryFn: () => getAccountDetail(accountId as string),
    enabled: Boolean(accountId),
  });
}

export function useReconciliationRuns(accountId: string | undefined) {
  return useQuery({
    queryKey: ["portfolio", "accounts", accountId, "reconciliation-runs"],
    queryFn: () => listReconciliationRuns(accountId as string),
    enabled: Boolean(accountId),
  });
}
