"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { useBacktests, useRunBacktest } from "@/lib/hooks/useBacktests";

export default function BacktestsPage() {
  const backtests = useBacktests();
  const run = useRunBacktest();

  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    run.mutate({
      date_range_start: dateStart || null,
      date_range_end: dateEnd || null,
    });
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Backtests
      </h1>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Run a new backtest
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Leave dates blank to use the full ~2-year ingested history. A run replays the active
            strategy version&apos;s scoring formula day-by-day and can take several seconds.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Start date
              </label>
              <Input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                End date
              </label>
              <Input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)} />
            </div>
          </div>
          <ErrorBanner error={run.error} />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={run.isPending}>
              {run.isPending ? "Running…" : "Run backtest"}
            </Button>
            {run.isPending && (
              <LoadingSpinner label="Replaying the scoring engine over the full history — this can take several seconds…" />
            )}
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Past runs</h2>
        {backtests.isLoading && <LoadingSpinner label="Loading backtests…" />}
        {backtests.error && <ErrorBanner error={backtests.error} />}
        {backtests.data && backtests.data.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No backtests run yet.</p>
        )}
        {backtests.data && backtests.data.length > 0 && (
          <Table>
            <Thead>
              <Tr>
                <Th>ID</Th>
                <Th>Date range</Th>
                <Th>Return</Th>
                <Th>Drawdown</Th>
                <Th>Trades</Th>
                <Th>Created</Th>
              </Tr>
            </Thead>
            <Tbody>
              {backtests.data.map((record) => (
                <Tr key={record.id}>
                  <Td>
                    <Link
                      href={`/backtests/${record.id}`}
                      className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      #{record.id}
                    </Link>
                  </Td>
                  <Td>
                    {record.date_range_start} → {record.date_range_end}
                  </Td>
                  <Td>{Number(record.results_summary.total_return_pct).toFixed(2)}%</Td>
                  <Td>{Number(record.results_summary.max_drawdown_pct).toFixed(2)}%</Td>
                  <Td>{record.results_summary.num_trades}</Td>
                  <Td>{new Date(record.created_at).toLocaleString()}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
