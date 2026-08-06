import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { OperatingModeStatus } from "@/components/layout/OperatingModeStatus";
import { IncompletePlanBanner } from "@/components/ui/IncompletePlanBanner";
import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { DataFreshnessBadge } from "@/components/ui/DataFreshnessBadge";
import { ApprovalRequiredBadge } from "@/components/ui/ApprovalRequiredBadge";
import { EvidenceCompletenessIndicator } from "@/components/ui/EvidenceCompletenessIndicator";
import { EventRiskWarning } from "@/components/ui/EventRiskWarning";
import { SourceTimestamp } from "@/components/ui/SourceTimestamp";
import { PageState } from "@/components/ui/PageState";
import { Card } from "@/components/ui/Card";

/**
 * The default landing route (docs/MORNING_PLAN_SPEC.md, FR-54). Fixed
 * seven-section grouping, rendered with synthetic example entries only —
 * no scheduler, no plan-assembly service, no recommendation data exists
 * yet (Revision Prompt R2 is scaffold/navigation only).
 */
const SECTIONS = [
  { key: "act-now", title: "Act Now", cap: 3 },
  { key: "approval-required", title: "Approval Required", cap: undefined },
  { key: "hold-manage", title: "Hold / Manage", cap: undefined },
  { key: "investment-watch", title: "Investment Watch", cap: undefined },
  { key: "tactical-watch", title: "Tactical Watch", cap: undefined },
  { key: "avoid", title: "Avoid", cap: undefined },
  { key: "data-problems", title: "Data Problems", cap: undefined },
] as const;

export default function MorningDashboardPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Morning Decision Dashboard
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          One official plan per U.S. trading day (docs/MORNING_PLAN_SPEC.md). Target: 06:10
          America/Los_Angeles, 20 minutes before the open.
        </p>
      </div>

      <ScaffoldNotice>
        No scheduler, plan-assembly service, or recommendation data exists yet — every card
        below is a synthetic example of the target layout.
      </ScaffoldNotice>

      <Card className="flex flex-wrap items-center gap-4">
        <SourceTimestamp
          source="Synthetic example"
          timestamp="2026-08-06T06:10:00-07:00"
          freshness="STALE"
        />
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Version: FINAL (example)</span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Next refresh: 05:45 tomorrow</span>
        <OperatingModeStatus />
      </Card>

      <IncompletePlanBanner
        reasons={["Example: fundamentals vendor unavailable for 2 of 48 watchlist names"]}
      />

      {SECTIONS.map((section) => (
        <Card key={section.key}>
          <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
            {section.title}
            {section.cap ? (
              <span className="ml-2 text-xs font-normal text-zinc-500 dark:text-zinc-400">
                (max {section.cap} shown)
              </span>
            ) : null}
          </h2>

          {section.key === "act-now" && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
                <span className="font-medium">AAPL (example)</span>
                <DecisionLaneBadge lane="TACTICAL" />
                <DataFreshnessBadge status="FRESH" asOf="06:08" />
                <EvidenceCompletenessIndicator available={5} total={5} />
              </div>
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
                <span className="font-medium">MSFT (example)</span>
                <DecisionLaneBadge lane="INVESTMENT" />
                <ApprovalRequiredBadge expiresAt="06:40" />
              </div>
            </div>
          )}

          {section.key === "approval-required" && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 p-3 text-sm dark:border-zinc-800">
              <span className="font-medium">NVDA (example)</span>
              <DecisionLaneBadge lane="TACTICAL" />
              <ApprovalRequiredBadge />
              <EventRiskWarning eventLabel="Earnings in 3 trading days (example)" />
            </div>
          )}

          {section.key === "data-problems" && (
            <PageState
              variant="disconnected"
              title="Example: fundamentals vendor unreachable"
              description="Affected names route here instead of being silently dropped or shown as complete."
            />
          )}

          {!["act-now", "approval-required", "data-problems"].includes(section.key) && (
            <PageState variant="no-action" title="No example entries for this section" />
          )}
        </Card>
      ))}
    </div>
  );
}
