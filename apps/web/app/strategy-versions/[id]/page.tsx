"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { Textarea } from "@/components/ui/Textarea";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { StatusPill } from "@/components/ui/StatusPill";
import { CompareView } from "@/components/strategy/CompareView";
import {
  useApproveStrategyVersion,
  useCompareStrategyVersion,
  useRejectStrategyVersion,
  useStrategyVersion,
} from "@/lib/hooks/useStrategyVersions";

export default function StrategyVersionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const version = useStrategyVersion(id);
  const compare = useCompareStrategyVersion();
  const approve = useApproveStrategyVersion();
  const reject = useRejectStrategyVersion();

  const [comment, setComment] = useState("");

  const isProposed = version.data?.status === "PROPOSED";

  return (
    <div className="flex flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          {version.data?.name ?? `Strategy version #${id}`}
        </h1>
        {version.data && <StatusPill status={version.data.status} />}
      </div>

      {version.isLoading && <LoadingSpinner label="Loading…" />}
      {version.error && <ErrorBanner error={version.error} />}

      {version.data && (
        <>
          <Card>
            <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Config</h2>
            <pre className="overflow-x-auto rounded-md bg-zinc-100 p-4 text-xs text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
              {JSON.stringify(version.data.config, null, 2)}
            </pre>
            {version.data.decision_comment && (
              <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
                <span className="font-medium">Decision comment:</span>{" "}
                {version.data.decision_comment}
              </p>
            )}
          </Card>

          {isProposed && (
            <Card>
              <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Review</h2>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <Button
                    variant="secondary"
                    disabled={compare.isPending}
                    onClick={() => compare.mutate({ id, params: {} })}
                  >
                    {compare.isPending ? "Comparing…" : "Compare against active"}
                  </Button>
                  {compare.isPending && (
                    <LoadingSpinner label="Running two backtests for comparison — this can take several seconds…" />
                  )}
                </div>
                <ErrorBanner error={compare.error} />

                {compare.data && <CompareView comparison={compare.data} />}

                <div>
                  <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Comment (optional)
                  </label>
                  <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} />
                </div>
                <ErrorBanner error={approve.error ?? reject.error} />
                <div className="flex items-center gap-3">
                  <ConfirmButton
                    label="Approve"
                    confirmLabel="Confirm approval"
                    disabled={approve.isPending || reject.isPending}
                    onConfirm={() => approve.mutate({ id, input: { comment: comment || null } })}
                  />
                  <ConfirmButton
                    label="Reject"
                    confirmLabel="Confirm rejection"
                    variant="danger"
                    disabled={approve.isPending || reject.isPending}
                    onConfirm={() => reject.mutate({ id, input: { comment: comment || null } })}
                  />
                  {(approve.isPending || reject.isPending) && (
                    <LoadingSpinner
                      label={
                        approve.isPending
                          ? "Approving — re-running the comparison…"
                          : "Rejecting…"
                      }
                    />
                  )}
                </div>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
