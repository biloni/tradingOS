import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { Card } from "@/components/ui/Card";
import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { SourceTimestamp } from "@/components/ui/SourceTimestamp";
import { PageState } from "@/components/ui/PageState";

/**
 * docs/PRODUCT_REQUIREMENTS.md FR-51/FR-59 — the Investment decision
 * lane (~3-24 month theses). Route placeholder only.
 */
export default function InvestmentPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Investment"
        description="3-24 month theses. Buy-and-hold is not a permanent promise (DQ-1) — every entry needs a valuation range, horizon, review date, catalysts, risks, and thesis-break conditions."
      />
      <ScaffoldNotice />
      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">MSFT (example)</span>
          <DecisionLaneBadge lane="INVESTMENT" />
        </div>
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Valuation range</dt>
            <dd>$380 - $430 (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Horizon</dt>
            <dd>12-18 months (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Review date</dt>
            <dd>2027-02-01 (example)</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
              Thesis-break condition
            </dt>
            <dd>Cloud revenue growth below 15% YoY for two consecutive quarters (example)</dd>
          </div>
        </dl>
        <SourceTimestamp source="Synthetic example" timestamp="2026-08-06T06:10:00-07:00" />
      </Card>
      <PageState variant="empty" description="No other Investment-lane entries yet." />
    </div>
  );
}
