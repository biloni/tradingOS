import { apiGet } from "./client";

export type RecommendationLevel = {
  kind: "ENTRY" | "STOP" | "TARGET";
  price: string;
  basis: string | null;
};

export type RecommendationVersionDetail = {
  id: string;
  version_number: number;
  action: string;
  confidence: "LOW" | "MEDIUM" | "HIGH";
  score: string | null;
  rationale: string;
  generated_at: string;
  levels: RecommendationLevel[];
  committee_session_id: string | null;
};

export type RecommendationDetail = {
  id: string;
  instrument: { id: string; ticker: string; name: string | null };
  status: string;
  opened_at: string;
  latest_version: RecommendationVersionDetail | null;
};

export function getRecommendation(id: string): Promise<RecommendationDetail> {
  return apiGet<RecommendationDetail>(`/api/v1/recommendations/${id}`);
}

/**
 * `MorningPlanItem.recommendation_version_id` (docs/MORNING_PLAN_SPEC.md's
 * version-scoped job-lineage manifest) is a `RecommendationVersion` id,
 * not a `Recommendation` id — this resolves one directly rather than
 * requiring a caller to already know the parent recommendation.
 */
export function getRecommendationVersion(versionId: string): Promise<RecommendationVersionDetail> {
  return apiGet<RecommendationVersionDetail>(`/api/v1/recommendations/versions/${versionId}`);
}

export type AgentOpinion = {
  stance: string | null;
  structured_output: Record<string, unknown>;
};

export type AgentRun = {
  id: string;
  role: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  opinion: AgentOpinion | null;
};

export type CommitteeSessionDetail = {
  id: string;
  instrument: { id: string; ticker: string; name: string | null };
  triggered_by: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  agent_runs: AgentRun[];
};

/**
 * "Committee disagreement" (Revision Prompt 15's one-click-access
 * requirement) is derived client-side purely for display — counting
 * distinct non-null stances among `agent_runs` — never used to compute
 * or alter a trading decision, which the backend already finalized when
 * it wrote the `RecommendationVersion`.
 */
export function getCommitteeSession(sessionId: string): Promise<CommitteeSessionDetail> {
  return apiGet<CommitteeSessionDetail>(`/api/v1/recommendations/committee-sessions/${sessionId}`);
}
