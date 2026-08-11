"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { StatusPill } from "@/components/ui/StatusPill";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { PageState } from "@/components/ui/PageState";
import { StepUpGate } from "@/components/ui/StepUpGate";
import { useOperatingMode } from "@/lib/hooks/useOperatingMode";
import {
  useApproveOrderApproval,
  useOrderApproval,
  useRefreshOrderApproval,
  useSubmitOrderApproval,
} from "@/lib/hooks/useOrderApproval";

// Mirrors apps/api/.env.example's documented default `ALPACA_BASE_URL` —
// shown as a fixed, non-editable confirmation fact (never an input the
// user could change): the whole point of a human-confirmation gate is
// confirming what's already true, not choosing a value (OA-6 fail-closed
// still re-validates this independently server-side regardless).
const PAPER_BROKER_ENDPOINT = "https://paper-api.alpaca.markets";

function BoundFieldRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-zinc-100 py-1.5 text-sm last:border-b-0 dark:border-zinc-800">
      <span className="text-zinc-500 dark:text-zinc-400">{label}</span>
      <span className="font-mono text-black dark:text-zinc-50">{value}</span>
    </div>
  );
}

export default function OrderApprovalPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data: approval, isLoading, isError, error } = useOrderApproval(id);
  const { data: operatingMode } = useOperatingMode();
  const canAttemptSubmission = approval?.status === "APPROVED" && operatingMode?.can_submit_orders;
  const refresh = useRefreshOrderApproval(canAttemptSubmission ? id : undefined);
  const approve = useApproveOrderApproval();
  const submit = useSubmitOrderApproval();
  const [emulationAcknowledged, setEmulationAcknowledged] = useState(false);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6 p-8">
        <PageHeader title="Order Approval" description="Loading…" />
        <PageState variant="loading" />
      </div>
    );
  }

  if (isError || !approval) {
    return (
      <div className="flex flex-col gap-6 p-8">
        <PageHeader title="Order Approval" description="This approval could not be loaded." />
        <ErrorBanner error={error} />
      </div>
    );
  }

  const bf = approval.bound_fields;

  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Order Approval"
        description="The bound fields below are an immutable snapshot, set once when this approval was created — they cannot change underneath you between now and submission."
      />

      <Card role="region" aria-label="Final immutable summary">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-lg font-medium text-black dark:text-zinc-50">
            Final immutable summary
          </h2>
          <StatusPill status={approval.status} />
        </div>
        <BoundFieldRow label="Side" value={bf.side} />
        <BoundFieldRow label="Quantity" value={bf.quantity} />
        <BoundFieldRow label="Order type" value={bf.order_type} />
        <BoundFieldRow label="Limit price" value={bf.limit_price ?? "market"} />
        <BoundFieldRow label="Stop price" value={bf.stop_price ?? "none"} />
        <BoundFieldRow label="Time in force" value={bf.time_in_force} />
        <BoundFieldRow label="Outside hours" value={bf.outside_hours ? "yes" : "no"} />
        <BoundFieldRow label="Max notional" value={bf.max_notional ?? "unlimited"} />
        <BoundFieldRow
          label="Quote price at approval"
          value={bf.quote_price_at_approval ?? "unavailable"}
        />
        <BoundFieldRow label="Integrity hash" value={approval.integrity_hash.slice(0, 16) + "…"} />
        <BoundFieldRow
          label="Expires at"
          value={new Date(approval.expires_at).toLocaleString()}
        />
      </Card>

      {approval.status === "PENDING" && (
        <Card>
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">Approve</h2>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            An approval past its expiry can no longer be approved — the server rejects it even if
            this page hasn&apos;t refreshed to reflect that yet.
          </p>
          <ErrorBanner
            error={approve.error}
            messages={{ 400: "This approval can no longer be approved (likely expired)." }}
          />
          <StepUpGate reason="approving an order authorizes it">
            <ConfirmButton
              label="Approve this order"
              confirmLabel="Yes, approve exactly as shown above"
              disabled={approve.isPending}
              onConfirm={() => approve.mutate({ id, approvedBy: "user" })}
            />
          </StepUpGate>
        </Card>
      )}

      {approval.status === "APPROVED" && operatingMode && !operatingMode.can_submit_orders && (
        <Card role="alert">
          <h2 className="mb-2 text-lg font-medium text-black dark:text-zinc-50">
            Submission is not available right now
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            The app is operating in {operatingMode.environment_label} mode, which cannot submit
            orders to a broker (see the banner at the top of every page). This approval stays
            valid — switch operating mode first, then come back to submit before it expires.
          </p>
        </Card>
      )}

      {approval.status === "APPROVED" && operatingMode?.can_submit_orders && (
        <Card>
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
            Immediately before submission
          </h2>
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            A fresh quote, buying power, open positions, and market-session check — recalculated
            now, not reused from approval time.
          </p>
          {refresh.isLoading && <LoadingSpinner label="Refreshing…" />}
          {refresh.error && <ErrorBanner error={refresh.error} />}
          {refresh.data && (
            <>
              <BoundFieldRow label="Current quote" value={refresh.data.quote_price ?? "unavailable"} />
              <BoundFieldRow
                label="Buying power"
                value={refresh.data.buying_power ?? "unavailable"}
              />
              <BoundFieldRow
                label="Open position quantity"
                value={refresh.data.open_position_quantity ?? "0"}
              />
              <BoundFieldRow label="Open order count" value={String(refresh.data.open_order_count)} />
              <BoundFieldRow
                label="Trading day"
                value={refresh.data.is_trading_day ? "yes" : `no — ${refresh.data.market_closed_reason ?? "closed"}`}
              />
              {refresh.data.requires_reapproval && (
                <p className="mt-2 text-sm font-medium text-amber-700 dark:text-amber-400" role="alert">
                  This order cannot be submitted: {refresh.data.reason ?? "blocked by a pre-submission check"}.
                </p>
              )}

              {!refresh.data.requires_reapproval && (
                <div className="mt-4 flex flex-col gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-800">
                  <label className="flex items-start gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                    <input
                      type="checkbox"
                      checked={emulationAcknowledged}
                      onChange={(e) => setEmulationAcknowledged(e.target.checked)}
                      className="mt-0.5"
                    />
                    I understand a bracket order may be emulated as separate orders rather than
                    natively supported by the broker, if applicable.
                  </label>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Environment: {operatingMode?.environment_label ?? "PAPER"} &middot; Broker
                    endpoint: {PAPER_BROKER_ENDPOINT}
                  </p>
                  <ErrorBanner error={submit.error} />
                  <StepUpGate reason="submitting to the broker is the final, hardest-to-reverse step">
                    <ConfirmButton
                      label="Submit to broker"
                      confirmLabel="Yes, submit exactly as shown above"
                      disabled={submit.isPending}
                      onConfirm={() =>
                        submit.mutate({
                          id,
                          input: {
                            requestedMode:
                              (operatingMode?.mode as
                                | "PAPER_MANUAL_APPROVAL"
                                | "PAPER_AUTO_POLICY") ?? "PAPER_MANUAL_APPROVAL",
                            lane: "TACTICAL",
                            sourceRecommendationVersionId: bf.recommendation_version_id,
                            emulationAcknowledged,
                            confirmation: {
                              confirmedAt: new Date().toISOString(),
                              accountId: bf.account_id,
                              environment: operatingMode?.environment_label ?? "PAPER",
                              brokerEndpoint: PAPER_BROKER_ENDPOINT,
                            },
                          },
                        })
                      }
                    />
                  </StepUpGate>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {submit.data && (
        <Card role="status">
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">Broker status</h2>
          <BoundFieldRow label="Attempt outcome" value={submit.data.attempt.outcome} />
          <BoundFieldRow label="Order status" value={submit.data.order_status ?? "none"} />
          <BoundFieldRow
            label="Used native bracket"
            value={submit.data.used_native_bracket ? "yes" : "no"}
          />
          {submit.data.disclosure && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              {submit.data.disclosure}
            </p>
          )}
          {submit.data.invalidated && (
            <p className="mt-2 text-sm font-medium text-red-700 dark:text-red-400" role="alert">
              Invalidated: {submit.data.invalidation_reason}
            </p>
          )}
        </Card>
      )}

      {(approval.status === "REJECTED" ||
        approval.status === "EXPIRED" ||
        approval.status === "INVALIDATED" ||
        approval.status === "SUBMITTED") && (
        <PageState
          variant="no-action"
          title={`This approval is ${approval.status.toLowerCase()} — no further action is possible here.`}
        />
      )}
    </div>
  );
}
