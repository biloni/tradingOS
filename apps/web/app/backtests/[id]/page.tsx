"use client";

import { useParams } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { BacktestReport } from "@/components/backtests/BacktestReport";
import { useBacktest } from "@/lib/hooks/useBacktests";

export default function BacktestDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const backtest = useBacktest(id);

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Backtest #{id}
      </h1>
      <Card>
        {backtest.isLoading && <LoadingSpinner label="Loading backtest…" />}
        {backtest.error && <ErrorBanner error={backtest.error} />}
        {backtest.data && <BacktestReport run={backtest.data} />}
      </Card>
    </div>
  );
}
