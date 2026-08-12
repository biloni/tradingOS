import { apiGet, apiPost } from "./client";

export type OrderApprovalStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED"
  | "INVALIDATED"
  | "SUBMITTED";

export type ApprovalBoundFields = {
  account_id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  quantity: string;
  order_type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT";
  limit_price: string | null;
  stop_price: string | null;
  time_in_force: string;
  outside_hours: boolean;
  attached_legs: Record<string, unknown>;
  max_notional: string | null;
  recommendation_version_id: string | null;
  quote_price_at_approval: string | null;
};

/**
 * `bound_fields` is the immutable snapshot (Revision Prompt 15's "final
 * immutable summary" requirement) — set once at `POST /order-approvals`
 * and never mutated afterward, matching `docs/DECISIONS.md` ADR-048.
 */
export type OrderApproval = {
  id: string;
  order_proposal_version_id: string;
  approved_by: string | null;
  requested_at: string;
  decided_at: string | null;
  expires_at: string;
  status: OrderApprovalStatus;
  integrity_hash: string;
  bound_fields: ApprovalBoundFields;
};

export function getOrderApproval(id: string): Promise<OrderApproval> {
  return apiGet<OrderApproval>(`/api/v1/order-approvals/${id}`);
}

/** The approval queue's real data source (`apps/app/approvals/page.tsx`).
 * Defaults server-side to `PENDING` only, matching what a human actually
 * needs to act on. */
export function listOrderApprovals(status?: OrderApprovalStatus): Promise<OrderApproval[]> {
  const query = status ? `?status=${status}` : "";
  return apiGet<OrderApproval[]>(`/api/v1/order-approvals${query}`);
}

export type PreSubmissionSnapshot = {
  quote_price: string | null;
  quote_observed_at: string | null;
  buying_power: string | null;
  open_position_quantity: string | null;
  open_order_count: number;
  is_trading_day: boolean;
  market_closed_reason: string | null;
  upcoming_earnings_report_date: string | null;
  requires_reapproval: boolean;
  reason: string | null;
};

/** ORDER FLOW steps 2-4 as a preview — never mutates anything server-side. */
export function refreshOrderApproval(id: string): Promise<PreSubmissionSnapshot> {
  return apiGet<PreSubmissionSnapshot>(`/api/v1/order-approvals/${id}/refresh`);
}

export function approveOrderApproval(id: string, approvedBy: string): Promise<OrderApproval> {
  return apiPost<OrderApproval>(`/api/v1/order-approvals/${id}/approve`, {
    approved_by: approvedBy,
  });
}

export function rejectOrderApproval(id: string): Promise<OrderApproval> {
  return apiPost<OrderApproval>(`/api/v1/order-approvals/${id}/reject`);
}

export type OrderSubmitResult = {
  attempt: {
    id: string;
    order_approval_id: string;
    attempted_at: string;
    environment_label: string;
    outcome: string;
    idempotency_key: string | null;
    detail: string | null;
    resulting_order_id: string | null;
  };
  order_id: string | null;
  order_status: string | null;
  invalidated: boolean;
  invalidation_reason: string | null;
  used_native_bracket: boolean;
  disclosure: string | null;
  stop_loss_order_id: string | null;
  take_profit_order_id: string | null;
};

export function submitOrderApproval(
  id: string,
  input: {
    requestedMode: "PAPER_MANUAL_APPROVAL" | "PAPER_AUTO_POLICY";
    lane: "INVESTMENT" | "TACTICAL";
    sourceRecommendationVersionId: string | null;
    emulationAcknowledged: boolean;
    confirmation: {
      confirmedAt: string;
      accountId: string;
      environment: string;
      brokerEndpoint: string;
    };
  },
): Promise<OrderSubmitResult> {
  return apiPost<OrderSubmitResult>(`/api/v1/order-approvals/${id}/submit`, {
    requested_mode: input.requestedMode,
    lane: input.lane,
    source_recommendation_version_id: input.sourceRecommendationVersionId,
    emulation_acknowledged: input.emulationAcknowledged,
    confirmation: {
      confirmed_at: input.confirmation.confirmedAt,
      account_id: input.confirmation.accountId,
      environment: input.confirmation.environment,
      broker_endpoint: input.confirmation.brokerEndpoint,
    },
  });
}
