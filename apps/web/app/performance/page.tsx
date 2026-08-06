import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { PageState } from "@/components/ui/PageState";

/** docs/UX_MAP.md "Performance" page. Route placeholder only. */
export default function PerformancePage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Performance"
        description="Realized/unrealized P&L, win rate, R-multiple, drawdown, benchmark comparison, and recommendation-vs-reality tracking."
      />
      <ScaffoldNotice />
      <PageState variant="empty" description="No closed trades in this window yet (example)." />
    </div>
  );
}
