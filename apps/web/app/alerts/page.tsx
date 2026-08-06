import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { PageState } from "@/components/ui/PageState";

/** docs/UX_MAP.md "Monitor & Alerts" page (alerts feed). Route placeholder only. */
export default function AlertsPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Alerts"
        description="In-app alerts feed for open positions and watchlist names crossing an alert-worthy threshold."
      />
      <ScaffoldNotice />
      <PageState variant="no-action" title="No new alerts (example)" />
    </div>
  );
}
