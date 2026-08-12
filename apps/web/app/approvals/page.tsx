"use client";

import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { PageState } from "@/components/ui/PageState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { useOrderApprovals } from "@/lib/hooks/useOrderApproval";

/**
 * docs/ORDER_AUTHORITY_MODEL.md — every order in APPROVAL_REQUIRED,
 * awaiting a human decision. Wired to the real GET /api/v1/order-approvals
 * list endpoint (added alongside end-to-end platform testing) — this
 * page was a Revision Prompt R2 placeholder with hardcoded example data
 * until now. Approve/reject/submit still only happen on the per-approval
 * detail page (`/approvals/[id]`); this is the queue view that links
 * there.
 */
export default function ApprovalQueuePage() {
  const approvals = useOrderApprovals();

  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Approval Queue"
        description="Orders that passed every deterministic gate but need an explicit confirmation before anything happens (OA-3/OA-5)."
      />
      <Card>
        {approvals.isLoading && <PageState variant="loading" />}
        {approvals.isError && <ErrorBanner error={approvals.error} />}
        {approvals.data && approvals.data.length === 0 && (
          <PageState variant="no-action" title="No orders awaiting approval right now" />
        )}
        {approvals.data && approvals.data.length > 0 && (
          <Table>
            <Thead>
              <Tr>
                <Th>Side</Th>
                <Th>Quantity</Th>
                <Th>Order type</Th>
                <Th>Status</Th>
                <Th>Requested</Th>
                <Th>Expires</Th>
              </Tr>
            </Thead>
            <Tbody>
              {approvals.data.map((approval) => (
                <Tr key={approval.id}>
                  <Td>
                    <Link
                      href={`/approvals/${approval.id}`}
                      className="text-blue-700 hover:underline dark:text-blue-400"
                    >
                      {approval.bound_fields.side}
                    </Link>
                  </Td>
                  <Td>{approval.bound_fields.quantity}</Td>
                  <Td>{approval.bound_fields.order_type}</Td>
                  <Td>
                    <StatusPill status={approval.status} />
                  </Td>
                  <Td>{new Date(approval.requested_at).toLocaleString()}</Td>
                  <Td>{new Date(approval.expires_at).toLocaleString()}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
