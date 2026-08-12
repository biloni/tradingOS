import { useMutation } from "@tanstack/react-query";
import { researchCompany } from "@/lib/api/earningsResearch";

export function useEarningsResearch() {
  return useMutation({ mutationFn: researchCompany });
}
