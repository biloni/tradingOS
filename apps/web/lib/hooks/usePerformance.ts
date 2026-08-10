import { useQuery } from "@tanstack/react-query";
import { getPortfolioPerformance } from "@/lib/api/performance";

export function usePortfolioPerformance(accountId: string | undefined) {
  return useQuery({
    queryKey: ["performance", "portfolio", accountId],
    queryFn: () => getPortfolioPerformance(accountId as string),
    enabled: Boolean(accountId),
  });
}
