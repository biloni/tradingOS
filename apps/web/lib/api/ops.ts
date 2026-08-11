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

/**
 * `_usd` fields are ADR-031 decimal-as-string, same as every other
 * money field in this app — convert with `Number(...)` only at the
 * point of display.
 */
export type CostBudgetStatus = {
  daily_spend_usd: string;
  daily_budget_usd: string;
  budget_remaining_usd: string;
  kill_switch_active: boolean;
  as_of: string;
};

export function getCostBudgetStatus(): Promise<CostBudgetStatus> {
  return apiGet<CostBudgetStatus>("/api/v1/ops/cost-budget");
}

/**
 * Revision Prompt 16, task: real always-on scheduler/worker process —
 * `core/scheduler.py`'s in-process APScheduler status.
 */
export type SchedulerStatus = {
  running: boolean;
  tick_interval_seconds: number;
  tick_count: number;
  last_tick_at: string | null;
  last_tick_error: string | null;
};

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return apiGet<SchedulerStatus>("/api/v1/ops/scheduler");
}
