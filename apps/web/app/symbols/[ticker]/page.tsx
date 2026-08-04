"use client";

import { useParams } from "next/navigation";
import { useBars, useIndicators } from "@/lib/hooks/useSymbols";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { CandlestickChart } from "@/components/charts/CandlestickChart";

export default function SymbolDetailPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker.toUpperCase();

  const bars = useBars(ticker);
  const indicators = useIndicators(ticker);

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        {ticker}
      </h1>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Price (last 90 days)
        </h2>
        {bars.isLoading && <LoadingSpinner label="Loading price history…" />}
        {bars.error && <ErrorBanner error={bars.error} />}
        {bars.data && bars.data.length > 0 && <CandlestickChart bars={bars.data} />}
        {bars.data && bars.data.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No price history available.</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Latest indicators{indicators.data?.[0] ? ` (as of ${indicators.data[0].as_of})` : ""}
        </h2>
        {indicators.isLoading && <LoadingSpinner label="Loading indicators…" />}
        {indicators.error && <ErrorBanner error={indicators.error} />}
        {indicators.data && indicators.data.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No indicators computed yet for this symbol.
          </p>
        )}
        {indicators.data && indicators.data.length > 0 && (
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {indicators.data.map((indicator) => (
              <div key={indicator.indicator_name}>
                <dt className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
                  {indicator.indicator_name}
                </dt>
                <dd className="text-lg font-semibold text-black dark:text-zinc-50">
                  {Number(indicator.value).toFixed(2)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </Card>
    </div>
  );
}
