import { useMutation } from "@tanstack/react-query";
import { askQuestion } from "@/lib/api/ask";

export function useAskQuestion() {
  return useMutation({ mutationFn: askQuestion });
}
