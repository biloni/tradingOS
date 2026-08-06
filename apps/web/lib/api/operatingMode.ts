import { apiGet } from "./client";

/**
 * Revision Prompt R2 scaffold. `mode`/`environment_label` come from
 * `GET /api/v1/settings/operating-mode` (apps/api, R2) — the environment
 * banner and operating-mode status component must read this response,
 * never store or infer the value client-side (PROJECT_INSTRUCTIONS.md's
 * v2 amendment).
 */
export type OperatingMode =
  | "RESEARCH_ONLY"
  | "PAPER_MANUAL_APPROVAL"
  | "PAPER_AUTO_POLICY"
  | "LIVE_CONFIRM_EACH_ORDER";

export type EnvironmentLabel = "RESEARCH" | "PAPER" | "LIVE";

export type OperatingModeResponse = {
  mode: OperatingMode;
  environment_label: EnvironmentLabel;
  can_submit_orders: boolean;
};

export function getOperatingMode(): Promise<OperatingModeResponse> {
  return apiGet<OperatingModeResponse>("/api/v1/settings/operating-mode");
}
