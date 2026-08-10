import Link from "next/link";
import type { MorningPlanItem } from "@/lib/api/morningPlan";
import { DecisionLaneBadge, type DecisionLane } from "@/components/ui/DecisionLaneBadge";
import { StatusPill } from "@/components/ui/StatusPill";
import { EvidenceDetails } from "@/components/dashboard/EvidenceDetails";

function parseLane(headline: string): DecisionLane | null {
  if (headline.includes("(INVESTMENT")) return "INVESTMENT";
  if (headline.includes("(TACTICAL")) return "TACTICAL";
  return null;
}

/**
 * One card per `MorningPlanItem`. "Use Investment and Tactical labels
 * everywhere" (Revision Prompt 15) — the lane badge is derived from the
 * headline text the backend already writes in that exact
 * `"{TICKER} ({LANE}) — {action}"` shape
 * (`services/morning_plan_generate.py`), so the label is never invented
 * client-side, only surfaced as a badge in addition to the text that
 * already carries it.
 */
export function DashboardCard({ item }: { item: MorningPlanItem }) {
  const lane = parseLane(item.headline);
  const confidence = item.card_detail.policy_result["confidence"];
  const approvalState = item.card_detail.user_broker_state["approval_state"];
  const orderApprovalId = item.card_detail.user_broker_state["order_approval_id"];

  return (
    <li className="flex flex-col gap-2 rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-black dark:text-zinc-50">{item.headline}</span>
        {lane && <DecisionLaneBadge lane={lane} />}
        {typeof confidence === "string" && (
          <span className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            Direction confidence: {confidence}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {typeof approvalState === "string" && approvalState !== "NOT_YET_PROPOSED" ? (
          <>
            <span className="text-zinc-500 dark:text-zinc-400">Order:</span>
            <StatusPill status={approvalState} />
            {typeof orderApprovalId === "string" && approvalState === "PENDING" && (
              <Link
                href={`/approvals/${orderApprovalId}`}
                className="rounded-md bg-black px-2.5 py-1 font-medium text-white hover:bg-zinc-800 dark:bg-zinc-50 dark:text-black dark:hover:bg-zinc-200"
              >
                Review &amp; approve
              </Link>
            )}
            {typeof orderApprovalId === "string" && approvalState !== "PENDING" && (
              <Link
                href={`/approvals/${orderApprovalId}`}
                className="text-zinc-600 underline hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100"
              >
                View order approval
              </Link>
            )}
          </>
        ) : (
          <span className="text-zinc-500 dark:text-zinc-400">
            No order proposal exists yet for this recommendation.
          </span>
        )}
      </div>

      <EvidenceDetails
        cardDetail={item.card_detail}
        recommendationVersionId={item.recommendation_version_id}
      />
    </li>
  );
}
