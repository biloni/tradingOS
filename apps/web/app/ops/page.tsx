"use client";

import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { PageState } from "@/components/ui/PageState";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { useJobRuns, useMetrics } from "@/lib/hooks/useOps";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-black dark:text-zinc-50">{value}</p>
    </div>
  );
}

function formatMs(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(0)}ms`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "in progress";
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export default function OpsPage() {
  const metrics = useMetrics();
  const jobRuns = useJobRuns(20);

  return (
    <div className="flex flex-col gap-6 p-8">
      <PageHeader
        title="Operations"
        description="Process metrics and the morning-plan job dashboard — this process's own request volume/latency, and the run history of the one recurring job this app has today."
      />

      <Card>
        <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
          Process metrics
        </h2>
        {metrics.isLoading && <PageState variant="loading" />}
        {metrics.isError && <ErrorBanner error={metrics.error} />}
        {metrics.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile label="Uptime" value={formatDuration(metrics.data.uptime_seconds)} />
            <StatTile label="Total requests" value={String(metrics.data.total_requests)} />
            <StatTile label="Avg latency" value={formatMs(metrics.data.latency.avg_ms)} />
            <StatTile label="p95 latency" value={formatMs(metrics.data.latency.p95_ms)} />
          </div>
        )}
        {metrics.data && Object.keys(metrics.data.status_class_counts).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            {Object.entries(metrics.data.status_class_counts).map(([statusClass, count]) => (
              <span
                key={statusClass}
                className="rounded-full bg-zinc-100 px-2.5 py-0.5 dark:bg-zinc-800"
              >
                {statusClass}: {count}
              </span>
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          In-process only — resets on restart, and reflects only this one server process.
        </p>
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-medium text-black dark:text-zinc-50">
          Morning plan job runs
        </h2>
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          No always-on scheduler is deployed yet — these are the runs of{" "}
          <code>decide_schedule()</code> triggered manually or by a local polling loop, most
          recent first.
        </p>
        {jobRuns.isLoading && <PageState variant="loading" />}
        {jobRuns.isError && <ErrorBanner error={jobRuns.error} />}
        {jobRuns.data && jobRuns.data.length === 0 && (
          <PageState variant="empty" title="No job runs recorded yet" />
        )}
        {jobRuns.data && jobRuns.data.length > 0 && (
          <Table>
            <Thead>
              <Tr>
                <Th>Plan date</Th>
                <Th>Status</Th>
                <Th>Triggered by</Th>
                <Th>Started</Th>
                <Th>Duration</Th>
                <Th>Error</Th>
              </Tr>
            </Thead>
            <Tbody>
              {jobRuns.data.map((run) => (
                <Tr key={run.id}>
                  <Td>{run.plan_date}</Td>
                  <Td>
                    <StatusPill status={run.status} />
                  </Td>
                  <Td>{run.triggered_by}</Td>
                  <Td>{new Date(run.started_at).toLocaleString()}</Td>
                  <Td>{formatDuration(run.duration_seconds)}</Td>
                  <Td className="max-w-xs truncate text-red-700 dark:text-red-400">
                    {run.error_detail ?? ""}
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
