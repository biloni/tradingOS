import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { PageState } from "@/components/ui/PageState";

/** docs/UX_MAP.md "Journal" page. Route placeholder only. */
export default function JournalPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Journal"
        description="Broker-agnostic trade log — what you actually did, wherever you did it."
      />
      <ScaffoldNotice />
      <PageState variant="empty" description="No journal entries yet (example)." />
    </div>
  );
}
