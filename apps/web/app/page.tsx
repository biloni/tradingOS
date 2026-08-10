"use client";

import type { MorningPlanItem, MorningPlanSectionKey } from "@/lib/api/morningPlan";
import { useMorningPlanDashboard } from "@/lib/hooks/useMorningPlanDashboard";
import { useDefaultAccount } from "@/lib/hooks/useAccounts";
import { usePortfolioPerformance } from "@/lib/hooks/usePerformance";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageState } from "@/components/ui/PageState";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { IncompletePlanBanner } from "@/components/ui/IncompletePlanBanner";
import { StatusStrip } from "@/components/dashboard/StatusStrip";
import { PortfolioStrip } from "@/components/dashboard/PortfolioStrip";
import { DashboardSection } from "@/components/dashboard/DashboardSection";

function itemsFor(
  sections: { section_key: MorningPlanSectionKey; items: MorningPlanItem[] }[],
  key: MorningPlanSectionKey,
): MorningPlanItem[] {
  return sections.find((s) => s.section_key === key)?.items ?? [];
}

/**
 * "Existing Positions" (Revision Prompt 15's primary layout) has no
 * dedicated backend section key — an open lot's guidance action already
 * routes it into Act Now / Buy and Hold / Tactical Earnings by what it
 * recommends doing next (docs/MORNING_PLAN_SPEC.md's Hold/Manage
 * classification). Rather than adding a new backend classification (out
 * of scope for a UX-only pass), this cross-cuts the sections that can
 * contain a holding and filters by the `lot_id` evidence field every
 * holding-derived card already carries — a symbol can legitimately
 * appear here *and* in its action section at once, the same "two
 * distinct entries, never merged" rule the spec already applies to
 * dual Investment/Tactical identity.
 */
function existingPositions(
  sections: { section_key: MorningPlanSectionKey; items: MorningPlanItem[] }[],
): MorningPlanItem[] {
  const candidateKeys: MorningPlanSectionKey[] = ["ACT_NOW", "BUY_AND_HOLD", "TACTICAL_TRADES"];
  return candidateKeys
    .flatMap((key) => itemsFor(sections, key))
    .filter((item) => typeof item.card_detail.evidence["lot_id"] === "string");
}

export default function MorningDashboardPage() {
  const { data, isLoading, isError, error } = useMorningPlanDashboard();
  const { data: account } = useDefaultAccount();
  const { data: performance } = usePortfolioPerformance(account?.id);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6 p-8">
        <PageHeader
          title="Morning Decision Dashboard"
          description="One official plan per U.S. trading day (docs/MORNING_PLAN_SPEC.md)."
        />
        <PageState variant="loading" title="Loading today's plan…" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col gap-6 p-8">
        <PageHeader
          title="Morning Decision Dashboard"
          description="One official plan per U.S. trading day (docs/MORNING_PLAN_SPEC.md)."
        />
        <ErrorBanner error={error} />
      </div>
    );
  }

  const { top_status: status, version } = data;

  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Morning Decision Dashboard"
        description="One official plan per U.S. trading day. Target: 06:10 America/Los_Angeles, 20 minutes before the open."
      />

      <StatusStrip status={status} />
      <PortfolioStrip status={status} performance={performance} />

      {status.plan_status === "MARKET_CLOSED" && (
        <PageState
          variant="market-closed"
          title="Market is closed"
          description={status.market_closed_reason ?? "No plan is generated on non-trading days."}
        />
      )}

      {status.plan_status !== "MARKET_CLOSED" && !version && (
        <PageState
          variant="empty"
          title={
            status.plan_status === "FAILED"
              ? "The last plan generation run failed"
              : "No plan has been generated yet today"
          }
          description="Run the plan generator, or check back after the 05:45/06:10 scheduled jobs."
        />
      )}

      {status.plan_status === "STALE" && version && (
        <IncompletePlanBanner
          reasons={[
            `This plan's evidence cutoff (${version.evidence_cutoff}) is older than the freshness threshold — treat it as a starting point, not current truth.`,
          ]}
        />
      )}

      {version && version.completeness_status === "INCOMPLETE" && (
        <IncompletePlanBanner
          reasons={version.quality_checks
            .filter((check) => !check.passed)
            .map((check) => check.detail ?? check.check_name)}
        />
      )}

      {version && (
        <>
          <DashboardSection
            title="Act Now"
            description="Passed every gate and is immediately actionable today. Capped at 3 by default."
            items={itemsFor(version.sections, "ACT_NOW")}
            cap={3}
            emptyTitle="Nothing needs action right now"
          />
          <DashboardSection
            title="Approval Required"
            description="Passed every gate but needs an explicit confirmation before anything happens."
            items={itemsFor(version.sections, "APPROVAL_REQUIRED")}
            emptyTitle="No approvals pending"
          />
          <DashboardSection
            title="Buy and Hold"
            description="Investment-lane names — 3-24 month thesis horizon."
            items={itemsFor(version.sections, "BUY_AND_HOLD")}
            emptyTitle="No Investment-lane entries"
          />
          <DashboardSection
            title="Tactical Earnings"
            description="Tactical-lane names — 1-10 day horizon, earnings-driven."
            items={itemsFor(version.sections, "TACTICAL_TRADES")}
            emptyTitle="No Tactical-lane entries"
          />
          <DashboardSection
            title="Existing Positions"
            description="Every open lot, cross-referenced from whichever action section its guidance routed it to (see note below)."
            items={existingPositions(version.sections)}
            emptyTitle="No open positions"
          />
          <DashboardSection
            title="Upcoming Events"
            description="Earnings reporting within the configured lookout window."
            items={itemsFor(version.sections, "UPCOMING_EVENTS")}
            emptyTitle="No upcoming earnings in the window"
          />
          <DashboardSection
            title="Watch/Avoid"
            description="Worth watching but not actionable today, or explicitly blocked by a gate."
            items={itemsFor(version.sections, "WATCH_AND_AVOID")}
            emptyTitle="Nothing on watch or avoid"
          />
          <DataAndJobHealthSection
            dataProblems={itemsFor(version.sections, "DATA_PROBLEMS")}
            qualityChecks={version.quality_checks}
            providerBrokerStatus={status.provider_broker_status}
          />
        </>
      )}
    </div>
  );
}

function DataAndJobHealthSection({
  dataProblems,
  qualityChecks,
  providerBrokerStatus,
}: {
  dataProblems: MorningPlanItem[];
  qualityChecks: { check_name: string; passed: boolean; detail: string | null }[];
  providerBrokerStatus: string;
}) {
  const failedChecks = qualityChecks.filter((check) => !check.passed);

  return (
    <section aria-label="Data and job health" className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">Data and Job Health</h2>
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        Provider/broker connectivity, the plan&apos;s own quality checks, and every symbol routed here
        because a required input was missing or stale — never silently dropped.
      </p>

      <div className="mb-4 flex items-center gap-2 text-sm">
        <span className="text-zinc-500 dark:text-zinc-400">Provider / broker:</span>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            providerBrokerStatus === "OK"
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
              : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
          }`}
        >
          {providerBrokerStatus}
        </span>
      </div>

      {failedChecks.length > 0 && (
        <div className="mb-4">
          <h3 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">
            Failed quality checks ({failedChecks.length})
          </h3>
          <ul className="flex flex-col gap-1 text-xs text-amber-800 dark:text-amber-300">
            {failedChecks.map((check) => (
              <li key={check.check_name}>{check.detail ?? check.check_name}</li>
            ))}
          </ul>
        </div>
      )}

      {dataProblems.length === 0 ? (
        <PageState variant="no-action" title="No symbols routed to Data Problems" />
      ) : (
        <ul className="flex flex-col gap-2">
          {dataProblems.map((item) => (
            <li
              key={item.id}
              className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950"
            >
              <span className="font-medium text-amber-900 dark:text-amber-200">{item.headline}</span>
              {typeof item.card_detail.policy_result["reason"] === "string" && (
                <p className="mt-1 text-xs text-amber-800 dark:text-amber-300">
                  {String(item.card_detail.policy_result["reason"])}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
