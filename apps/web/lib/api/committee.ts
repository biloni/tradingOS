import { apiGet } from "./client";

export type RoleRun = {
  role: string;
  display_name: string;
  status: "SUCCEEDED" | "FAILED" | "DEGRADED";
  error_detail: string | null;
  output: Record<string, unknown> | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  cost_usd: string;
};

export type CommitteeRun = {
  session_id: string;
  lane: "INVESTMENT" | "TACTICAL";
  status: string;
  role_runs: RoleRun[];
  total_cost_usd: string;
  recommendation_id: string | null;
  lane_action: string | null;
  veto_override_applied: boolean;
};

/** `GET /committee/sessions/{id}` — the review screen's one data source,
 * reconstructed from the persisted audit trail (never re-runs anything). */
export function getCommitteeSession(sessionId: string): Promise<CommitteeRun> {
  return apiGet<CommitteeRun>(`/api/v1/committee/sessions/${sessionId}`);
}
