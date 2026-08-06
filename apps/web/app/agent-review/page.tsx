import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { Card } from "@/components/ui/Card";
import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { EvidenceCompletenessIndicator } from "@/components/ui/EvidenceCompletenessIndicator";
import { SourceTimestamp } from "@/components/ui/SourceTimestamp";

/**
 * docs/UX_MAP.md "Committee / Recommendation detail" page, renamed
 * "Agent Review" per Revision Prompt R2's route list. Route placeholder
 * only — the 8-role committee is not wired up yet (Phase 8 seeded one
 * synthetic example; this page does not call that endpoint this pass).
 */
export default function AgentReviewPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Agent Review"
        description="The full 8-role committee output — Bull/Bear/Technical/Fundamental/Macro, then Risk/PM, then the CIO's final synthesis — with every cited evidence item and gate result."
      />
      <ScaffoldNotice />
      <Card className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="font-medium">AAPL (example)</span>
          <DecisionLaneBadge lane="TACTICAL" />
        </div>
        <EvidenceCompletenessIndicator available={4} total={5} missingCategories={["Fundamentals"]} />
        <SourceTimestamp source="Committee run (example)" timestamp="2026-08-06T06:04:00-07:00" />
      </Card>
    </div>
  );
}
