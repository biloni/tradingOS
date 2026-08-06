import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { DataFreshnessBadge } from "@/components/ui/DataFreshnessBadge";
import { Card } from "@/components/ui/Card";

/** docs/UX_MAP.md "Watchlist" page. Route placeholder only. */
export default function WatchlistsPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Watchlists"
        description="Tiered watchlist membership, monitoring frequency, and symbol-validation status."
      />
      <ScaffoldNotice />
      <Card className="flex flex-wrap items-center gap-3">
        <span className="font-medium">AAPL (example)</span>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Tier 1 &middot; Daily</span>
        <DataFreshnessBadge status="FRESH" asOf="06:08" />
      </Card>
    </div>
  );
}
