import { PageHeader } from "@/components/layout/PageHeader";
import { ScaffoldNotice } from "@/components/layout/ScaffoldNotice";
import { OperatingModeStatus } from "@/components/layout/OperatingModeStatus";
import { Card } from "@/components/ui/Card";

/**
 * docs/UX_MAP.md's top-bar operating-mode indicator, surfaced here too
 * as a dedicated settings surface. The status shown is read-only
 * (nonfunctional) this pass — a real mode selector is future scope and
 * must never widen server-side authorization regardless of what it
 * displays (FR-58).
 */
export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Settings"
        description="Operating mode, provider status, and risk-policy configuration."
      />
      <ScaffoldNotice>
        The operating-mode status below is read-only — changing it here is not implemented, and
        no UI control can widen what the server actually authorizes.
      </ScaffoldNotice>
      <Card className="flex flex-col gap-2">
        <h2 className="text-lg font-medium text-black dark:text-zinc-50">Operating mode</h2>
        <OperatingModeStatus />
      </Card>
    </div>
  );
}
