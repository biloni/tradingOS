"use client";

import { useState } from "react";
import type { MorningPlanCardDetail } from "@/lib/api/morningPlan";
import { useCommitteeSession, useRecommendationVersion } from "@/lib/hooks/useRecommendationDetail";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <p className="text-xs text-zinc-500 dark:text-zinc-400">None recorded.</p>;
  }
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-zinc-500 dark:text-zinc-400">{key.replace(/_/g, " ")}</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">
            {typeof value === "object" && value !== null ? JSON.stringify(value) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function stanceCounts(stances: (string | null)[]): { bullish: number; bearish: number; neutral: number } {
  let bullish = 0;
  let bearish = 0;
  let neutral = 0;
  for (const stance of stances) {
    if (stance === "BULLISH") bullish += 1;
    else if (stance === "BEARISH") bearish += 1;
    else neutral += 1;
  }
  return { bullish, bearish, neutral };
}

/**
 * "Committee disagreement" (Revision Prompt 15's evidence/audit
 * requirement) — a plain count of how many of this session's roles
 * landed on each stance. This is a display aggregation only; it never
 * feeds back into the recommendation the committee already produced.
 */
function CommitteeDisagreement({ sessionId }: { sessionId: string }) {
  const { data, isLoading, isError, error } = useCommitteeSession(sessionId);

  if (isLoading) return <LoadingSpinner label="Loading committee session…" />;
  if (isError || !data) return <ErrorBanner error={error} />;

  const stances = data.agent_runs.map((run) => run.opinion?.stance ?? null);
  const counts = stanceCounts(stances);
  const disagrees = counts.bullish > 0 && counts.bearish > 0;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs">
        <span className="font-medium text-black dark:text-zinc-50">
          {disagrees ? "Committee disagreed: " : "Committee agreed: "}
        </span>
        {counts.bullish} bullish, {counts.bearish} bearish, {counts.neutral} neutral (of{" "}
        {data.agent_runs.length} roles)
      </p>
      <ul className="flex flex-col gap-1 text-xs">
        {data.agent_runs.map((run) => (
          <li key={run.id} className="flex items-center gap-2">
            <span className="font-mono text-zinc-500 dark:text-zinc-400">
              {run.role.replace(/_/g, " ").toLowerCase()}
            </span>
            <span className="text-zinc-800 dark:text-zinc-200">
              {run.opinion?.stance ?? "no opinion recorded"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * "Risk calculations" — the recommendation version's own entry/stop/
 * target levels (`RecommendationLevel`, already computed server-side by
 * the HES pipeline) plus its score/confidence, exactly as stored. "Audit
 * history" is this version's own number and generation timestamp — the
 * full multi-version timeline a recommendation could in principle expose
 * is recorded as known UX debt (docs/UX_MAP.md), not fabricated here.
 */
function RecommendationRiskAndAudit({ recommendationVersionId }: { recommendationVersionId: string }) {
  const { data: version, isLoading, isError, error } = useRecommendationVersion(recommendationVersionId);

  if (isLoading) return <LoadingSpinner label="Loading recommendation…" />;
  if (isError || !version) {
    return <ErrorBanner error={error ?? new Error("Recommendation version not found.")} />;
  }

  return (
    <div className="flex flex-col gap-2 text-xs">
      <p>
        <span className="font-medium text-black dark:text-zinc-50">Score:</span> {version.score ?? "n/a"}{" "}
        &middot; <span className="font-medium text-black dark:text-zinc-50">Confidence:</span>{" "}
        {version.confidence}
      </p>
      {version.levels.length > 0 ? (
        <table className="w-full text-left">
          <thead className="text-zinc-500 dark:text-zinc-400">
            <tr>
              <th className="pr-3 font-normal">Level</th>
              <th className="font-normal">Price</th>
            </tr>
          </thead>
          <tbody>
            {version.levels.map((level) => (
              <tr key={level.kind}>
                <td className="pr-3 text-zinc-800 dark:text-zinc-200">{level.kind}</td>
                <td className="text-zinc-800 dark:text-zinc-200">{level.price}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-zinc-500 dark:text-zinc-400">No entry/stop/target levels recorded.</p>
      )}
      <p className="text-zinc-500 dark:text-zinc-400">
        Audit: recommendation version {version.version_number}, generated{" "}
        <time dateTime={version.generated_at}>{new Date(version.generated_at).toLocaleString()}</time>.
      </p>
      {version.committee_session_id && (
        <CommitteeDisagreement sessionId={version.committee_session_id} />
      )}
      {!version.committee_session_id && (
        <p className="text-zinc-500 dark:text-zinc-400">
          No committee session linked to this version (deterministic-only path).
        </p>
      )}
    </div>
  );
}

/**
 * One-click access to sources, committee disagreement, risk
 * calculations, and audit history (Revision Prompt 15) — a native
 * `<details>` disclosure rather than a modal dialog, the same
 * "not a modal, a second explicit interaction is enough" precedent
 * `components/ui/ConfirmButton.tsx` already established for this
 * single-user app. The five `card_detail` keys render immediately (no
 * extra request); the recommendation-scoped risk/audit/committee data
 * only fetches once the disclosure is actually opened.
 */
export function EvidenceDetails({
  cardDetail,
  recommendationVersionId,
}: {
  cardDetail: MorningPlanCardDetail;
  recommendationVersionId: string | null;
}) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className="mt-2 rounded-md border border-zinc-200 dark:border-zinc-800"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer select-none px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50 dark:text-zinc-400 dark:hover:bg-zinc-900">
        Sources, committee disagreement, risk, and audit history
      </summary>
      <div className="flex flex-col gap-3 border-t border-zinc-200 p-3 dark:border-zinc-800">
        <div>
          <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">Evidence</h4>
          <KeyValueList data={cardDetail.evidence} />
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">
            Deterministic calculations
          </h4>
          <KeyValueList data={cardDetail.deterministic} />
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">AI synthesis</h4>
          <KeyValueList data={cardDetail.ai_synthesis} />
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">Policy result</h4>
          <KeyValueList data={cardDetail.policy_result} />
        </div>
        <div>
          <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">
            User / broker state
          </h4>
          <KeyValueList data={cardDetail.user_broker_state} />
        </div>
        {recommendationVersionId && (
          <div>
            <h4 className="mb-1 text-xs font-semibold text-black dark:text-zinc-50">
              Risk calculations, committee disagreement, and audit history
            </h4>
            {open ? (
              <RecommendationRiskAndAudit recommendationVersionId={recommendationVersionId} />
            ) : (
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Expand to load risk levels, committee opinions, and audit history.
              </p>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
