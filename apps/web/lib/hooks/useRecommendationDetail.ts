import { useQuery } from "@tanstack/react-query";
import {
  getCommitteeSession,
  getRecommendation,
  getRecommendationVersion,
} from "@/lib/api/recommendations";

export function useRecommendation(id: string | undefined) {
  return useQuery({
    queryKey: ["recommendations", id],
    queryFn: () => getRecommendation(id as string),
    enabled: Boolean(id),
  });
}

export function useRecommendationVersion(versionId: string | undefined) {
  return useQuery({
    queryKey: ["recommendations", "versions", versionId],
    queryFn: () => getRecommendationVersion(versionId as string),
    enabled: Boolean(versionId),
  });
}

export function useCommitteeSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: ["committee-sessions", sessionId],
    queryFn: () => getCommitteeSession(sessionId as string),
    enabled: Boolean(sessionId),
  });
}
