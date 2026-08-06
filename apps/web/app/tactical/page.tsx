import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { Card } from "@/components/ui/Card";
import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { SourceTimestamp } from "@/components/ui/SourceTimestamp";
import { PageState } from "@/components/ui/PageState";

/**
 * docs/PRODUCT_REQUIREMENTS.md FR-51/FR-59 — the Tactical decision lane
 * (~1-10 trading-day setups). Route placeholder only.
 */
export default function TacticalPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Tactical Trades"
        description="1-10 trading-day setups. Every plan needs entry conditions, size, stop logic, targets, time exit, event risk, and cancellation conditions (DQ-2)."
      />
      <ScaffoldNotice />
      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">AAPL (example)</span>
          <DecisionLaneBadge lane="TACTICAL" />
        </div>
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Entry</dt>
            <dd>Above $232.50 (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Stop</dt>
            <dd>$227.00, ATR-based (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Target</dt>
            <dd>$244.00 (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Time exit</dt>
            <dd>10 trading days (example)</dd>
          </div>
        </dl>
        <SourceTimestamp source="Synthetic example" timestamp="2026-08-06T06:10:00-07:00" />
      </Card>
      <PageState variant="empty" description="No other Tactical-lane entries yet." />
    </div>
  );
}
