"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { PageState } from "@/components/ui/PageState";
import { StatusPill } from "@/components/ui/StatusPill";
import { useCommitteeSession } from "@/lib/hooks/useCommittee";
import type { RoleRun } from "@/lib/api/committee";

function RoleRunCard({ roleRun }: { roleRun: RoleRun }) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-black dark:text-zinc-50">{roleRun.display_name}</span>
        <StatusPill status={roleRun.status} />
        {roleRun.model && (
          <span className="text-xs text-zinc-500 dark:text-zinc-400">{roleRun.model}</span>
        )}
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-zinc-500 dark:text-zinc-400">
        <span>{roleRun.input_tokens} in / {roleRun.output_tokens} out tokens</span>
        <span>{roleRun.latency_ms}ms</span>
        <span>${roleRun.cost_usd}</span>
      </div>
      {roleRun.error_detail && (
        <p className="text-sm text-red-700 dark:text-red-400" role="alert">
          {roleRun.error_detail}
        </p>
      )}
      {roleRun.output && (
        <dl className="mt-1 grid grid-cols-1 gap-x-4 gap-y-1 border-t border-zinc-100 pt-2 text-sm dark:border-zinc-800 sm:grid-cols-2">
          {Object.entries(roleRun.output).map(([key, value]) => (
            <div key={key} className="flex flex-col">
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">{key}</dt>
              <dd className="break-words text-black dark:text-zinc-50">
                {typeof value === "string" ? value : JSON.stringify(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

/**
 * docs/UX_MAP.md "Committee / Recommendation detail" page, renamed
 * "Agent Review" per Revision Prompt R2's route list. Wired to the real
 * GET /committee/sessions/{id} review endpoint (added alongside
 * end-to-end platform testing) — this page was a Revision Prompt R2
 * placeholder with hardcoded example data until now. There is no
 * trigger-a-run UI here by design (matches this endpoint's own
 * docstring: "running a committee is a synchronous, explicitly-triggered,
 * human-reviewed action" assembled from real evidence/deterministic
 * inputs, not a form) — this page reviews a session that already ran.
 */
export default function AgentReviewPage() {
  // `useSearchParams()` returns null outside a Router context (e.g. this
  // component rendered directly in a unit test without Next's app router)
  // — a real, previously-crashing bug this file's own test caught.
  const searchParams = useSearchParams();
  const initialSessionId = searchParams?.get("session_id") ?? "";
  const [sessionIdInput, setSessionIdInput] = useState(initialSessionId);
  const [lookupId, setLookupId] = useState(initialSessionId || undefined);

  const session = useCommitteeSession(lookupId);

  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Agent Review"
        description="The full committee output — every role, then the CIO's final synthesis — with cost, latency, and cited output per role."
      />

      <Card>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            setLookupId(sessionIdInput.trim() || undefined);
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-600 dark:text-zinc-400">Session ID</span>
            <input
              type="text"
              value={sessionIdInput}
              onChange={(e) => setSessionIdInput(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="w-96 rounded-md border border-zinc-300 px-3 py-1.5 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <button
            type="submit"
            className="rounded-md bg-black px-3 py-1.5 text-sm font-medium text-white dark:bg-zinc-50 dark:text-black"
          >
            Load session
          </button>
        </form>
      </Card>

      {!lookupId && (
        <PageState
          variant="empty"
          title="Enter a committee session ID above"
          description="A session ID is produced by POST /api/v1/committee/{lane}/{instrument_id}/run — this page reviews an existing run, it does not trigger one."
        />
      )}
      {session.isLoading && <PageState variant="loading" />}
      {session.isError && <ErrorBanner error={session.error} />}
      {session.data && (
        <>
          <Card className="flex flex-wrap items-center gap-3">
            <span className="font-medium text-black dark:text-zinc-50">{session.data.lane}</span>
            <StatusPill status={session.data.status} />
            <span className="text-sm text-zinc-600 dark:text-zinc-400">
              Total cost: ${session.data.total_cost_usd}
            </span>
            {session.data.lane_action && (
              <span className="text-sm text-zinc-600 dark:text-zinc-400">
                Lane action: {session.data.lane_action}
              </span>
            )}
            {session.data.veto_override_applied && (
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                Deterministic veto override applied
              </span>
            )}
          </Card>
          {session.data.role_runs.map((roleRun) => (
            <RoleRunCard key={roleRun.role} roleRun={roleRun} />
          ))}
        </>
      )}
    </div>
  );
}
