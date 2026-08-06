import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { Card } from "@/components/ui/Card";
import { ApprovalRequiredBadge } from "@/components/ui/ApprovalRequiredBadge";
import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { OrderStateTimeline } from "@/components/ui/OrderStateTimeline";
import { PageState } from "@/components/ui/PageState";

/**
 * docs/ORDER_AUTHORITY_MODEL.md — every order in APPROVAL_REQUIRED,
 * awaiting a human decision. Route placeholder only; approving/rejecting
 * is not wired (no submission behavior exists in this revision).
 */
export default function ApprovalQueuePage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Approval Queue"
        description="Orders that passed every deterministic gate but need an explicit confirmation before anything happens (OA-3/OA-5)."
      />
      <ScaffoldNotice>
        Approve/reject actions are not implemented this pass — no order can be submitted from
        this page.
      </ScaffoldNotice>
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">JPM (example)</span>
          <DecisionLaneBadge lane="TACTICAL" />
          <ApprovalRequiredBadge expiresAt="06:40 (example)" />
        </div>
        <OrderStateTimeline
          steps={[
            { label: "Draft", status: "done" },
            { label: "Approval Required", status: "current" },
            { label: "Approved", status: "pending" },
            { label: "Submitted", status: "pending" },
            { label: "Filled", status: "pending" },
          ]}
        />
      </Card>
      <PageState variant="no-action" title="No other orders awaiting approval (example)" />
    </div>
  );
}
