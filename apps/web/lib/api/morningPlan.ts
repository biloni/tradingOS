import { apiGet } from "./client";

export type MorningPlanSectionKey =
  | "ACT_NOW"
  | "APPROVAL_REQUIRED"
  | "HOLD_MANAGE"
  | "INVESTMENT_WATCH"
  | "TACTICAL_WATCH"
  | "AVOID"
  | "DATA_PROBLEMS"
  | "BUY_AND_HOLD"
  | "TACTICAL_TRADES"
  | "WATCH_AND_AVOID"
  | "UPCOMING_EVENTS";

export type MorningPlanVersionLabel = "PRELIMINARY" | "FINAL" | "AD_HOC" | "CORRECTION";
export type PlanCompletenessStatus = "COMPLETE" | "INCOMPLETE" | "NO_ACTION" | "FAILED";

/**
 * `card_detail`'s five fixed keys (docs/MORNING_PLAN_SPEC.md /
 * services/morning_plan_generate.py): evidence, deterministic
 * calculations, AI synthesis, policy result, and user/broker state —
 * always present, sometimes empty objects. Never merged into one blob
 * client-side; each drill-in surface reads its own key so the
 * evidence-vs-inference distinction the backend deliberately keeps
 * separate stays visible in the UI too.
 */
export type MorningPlanCardDetail = {
  evidence: Record<string, unknown>;
  deterministic: Record<string, unknown>;
  ai_synthesis: Record<string, unknown>;
  policy_result: Record<string, unknown>;
  user_broker_state: Record<string, unknown>;
};

export type MorningPlanItem = {
  id: string;
  recommendation_version_id: string | null;
  instrument_id: string | null;
  display_order: number;
  headline: string;
  action_label: string | null;
  card_detail: MorningPlanCardDetail;
};

export type MorningPlanSection = {
  section_key: MorningPlanSectionKey;
  display_order: number;
  items: MorningPlanItem[];
};

export type MorningPlanQualityCheck = {
  check_name: string;
  passed: boolean;
  detail: string | null;
};

export type MorningPlanDeliveryEvent = {
  channel: "IN_APP" | "COWORK" | "MARKDOWN_EXPORT";
  status: string;
  delivered_at: string | null;
};

export type MorningPlanVersionDetail = {
  id: string;
  morning_plan_run_id: string;
  plan_date: string;
  version_label: MorningPlanVersionLabel;
  version_number: number;
  evidence_cutoff: string;
  generated_at: string;
  completeness_status: PlanCompletenessStatus;
  sections: MorningPlanSection[];
  quality_checks: MorningPlanQualityCheck[];
  delivery_events: MorningPlanDeliveryEvent[];
};

export type TopStatus = {
  market_date: string;
  is_trading_day: boolean;
  market_closed_reason: string | null;
  countdown_to_open_seconds: number | null;
  plan_status: string;
  plan_version_id: string | null;
  plan_version_label: MorningPlanVersionLabel | null;
  generated_at: string | null;
  evidence_cutoff: string | null;
  provider_broker_status: string;
  regime_classification: string | null;
  vix_proxy_level: string | null;
  vix_percentile: string | null;
  total_equity: string;
  cash: string;
  exposure_pct: string;
  risk_budget_pct: string | null;
  operating_mode: string;
  kill_switch_active: boolean;
};

export type DashboardResponse = {
  top_status: TopStatus;
  version: MorningPlanVersionDetail | null;
};

export function getMorningPlanDashboard(params?: {
  planDate?: string;
  now?: string;
}): Promise<DashboardResponse> {
  const query = new URLSearchParams();
  if (params?.planDate) query.set("plan_date", params.planDate);
  if (params?.now) query.set("now", params.now);
  const qs = query.toString();
  return apiGet<DashboardResponse>(`/api/v1/morning-plan/dashboard${qs ? `?${qs}` : ""}`);
}
