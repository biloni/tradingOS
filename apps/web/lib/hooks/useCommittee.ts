import { useQuery } from "@tanstack/react-query";
import { getCommitteeSession } from "@/lib/api/committee";

export function useCommitteeSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: ["committee", "sessions", sessionId],
    queryFn: () => getCommitteeSession(sessionId as string),
    enabled: Boolean(sessionId),
  });
}
