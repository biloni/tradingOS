import { apiGet } from "./client";

export type LatencyStats = {
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  sample_size: number;
};

export type Metrics = {
  uptime_seconds: number;
  total_requests: number;
  status_class_counts: Record<string, number>;
  latency: LatencyStats;
};

export type MorningPlanRunStatus = "RUNNING" | "COMPLETED" | "FAILED";

export type JobRun = {
  id: string;
  plan_date: string;
  status: MorningPlanRunStatus;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  error_detail: string | null;
};

export function getMetrics(): Promise<Metrics> {
  return apiGet<Metrics>("/api/v1/ops/metrics");
}

export function listJobRuns(limit = 20): Promise<JobRun[]> {
  return apiGet<JobRun[]>(`/api/v1/ops/job-runs?limit=${limit}`);
}
