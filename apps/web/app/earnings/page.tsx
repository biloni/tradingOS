import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { Card } from "@/components/ui/Card";
import { EventRiskWarning } from "@/components/ui/EventRiskWarning";
import { ApprovalRequiredBadge } from "@/components/ui/ApprovalRequiredBadge";
import { PageState } from "@/components/ui/PageState";

/**
 * docs/HYBRID_EARNINGS_STRATEGY.md — pre/post-event workflow. Route
 * placeholder only; no earnings-direction score exists yet.
 */
export default function EarningsCenterPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Earnings Center"
        description="Pre-event (6/8 conservative live threshold, 0.25%/0.50% risk budget) and post-event (three independent confirmation gates) earnings workflow."
      />
      <ScaffoldNotice />
      <Card className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">NVDA (example)</span>
          <ApprovalRequiredBadge />
        </div>
        <EventRiskWarning
          eventLabel="Earnings after close, 2026-08-08 (example)"
          detail="Direction score 5/8 (example) — below the 6/8 conservative live threshold; paper modes only."
        />
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
              Pre-event risk budget
            </dt>
            <dd>0.25% of equity (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
              Concurrent earnings trades
            </dt>
            <dd>1 of 3 max (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
              Post-event gates
            </dt>
            <dd>Not yet announced (example)</dd>
          </div>
        </dl>
      </Card>
      <PageState variant="market-closed" description="No other earnings events in the pre-event window right now (example)." />
    </div>
  );
}
