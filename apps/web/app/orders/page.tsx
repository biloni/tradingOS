import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { OperatingModeStatus } from "@/components/layout/OperatingModeStatus";
import { Card } from "@/components/ui/Card";
import { OrderStateTimeline } from "@/components/ui/OrderStateTimeline";
import { PageState } from "@/components/ui/PageState";

/**
 * docs/ORDER_AUTHORITY_MODEL.md / docs/UX_MAP.md's new Orders page — the
 * lifecycle surface distinct from Journal (what the user says they did)
 * and Portfolio/"Paper Sandbox" (Alpaca's own state). Route placeholder
 * only — no submit/cancel/kill-switch behavior exists this pass.
 */
export default function OrdersAndFillsPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Orders and Fills"
        description="This app's own order lifecycle: draft, approval, paper execution, and (later) live-confirmed execution."
      />
      <ScaffoldNotice>No submit, cancel, kill-switch, or cancel-all behavior is wired yet.</ScaffoldNotice>

      <Card className="flex flex-wrap items-center gap-4">
        <OperatingModeStatus />
        <span
          data-testid="kill-switch-placeholder"
          className="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-400 dark:border-zinc-700"
          aria-disabled="true"
        >
          Kill switch (not implemented)
        </span>
        <span
          data-testid="cancel-all-placeholder"
          className="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-400 dark:border-zinc-700"
          aria-disabled="true"
        >
          Cancel open orders (not implemented)
        </span>
      </Card>

      <Card className="flex flex-col gap-3">
        <span className="font-medium">JPM &mdash; BUY 5 (example)</span>
        <OrderStateTimeline
          steps={[
            { label: "Draft", status: "done" },
            { label: "Approval Required", status: "done" },
            { label: "Approved", status: "done" },
            { label: "Paper Submitted", status: "current" },
            { label: "Filled", status: "pending" },
          ]}
        />
      </Card>

      <Card className="flex flex-col gap-3">
        <span className="font-medium">SPY &mdash; SELL 2 (example, invalidated)</span>
        <OrderStateTimeline
          steps={[
            { label: "Draft", status: "done" },
            { label: "Approval Required", status: "done" },
            { label: "Invalidated", status: "invalidated" },
          ]}
        />
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Example reason: price moved beyond the configured invalidation threshold before
          submission.
        </p>
      </Card>

      <PageState variant="empty" title="No other orders yet" />
    </div>
  );
}
