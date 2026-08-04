import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getBacktest, listBacktests, runBacktest } from "@/lib/api/backtests";

export function useBacktests() {
  return useQuery({ queryKey: ["backtests"], queryFn: listBacktests });
}

export function useBacktest(id: number) {
  return useQuery({
    queryKey: ["backtests", id],
    queryFn: () => getBacktest(id),
    enabled: Number.isFinite(id),
  });
}

export function useRunBacktest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: runBacktest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });
}
