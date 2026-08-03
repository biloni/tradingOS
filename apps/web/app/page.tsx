"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api-client";

export default function Home() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
  });

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 bg-zinc-50 p-16 font-sans dark:bg-black">
      <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
        TradingOS
      </h1>
      <p className="max-w-md text-center text-zinc-600 dark:text-zinc-400">
        Decision-support for 2&ndash;10 day swing trades. Research and paper-trading mode
        only &mdash; no live orders are placed.
      </p>
      <div
        data-testid="api-status"
        className="rounded-lg border border-zinc-200 bg-white px-6 py-4 text-sm dark:border-zinc-800 dark:bg-zinc-900"
      >
        {isLoading && <span className="text-zinc-500">Checking API status&hellip;</span>}
        {error && (
          <span className="text-red-600 dark:text-red-400">
            API unreachable: {(error as Error).message}
          </span>
        )}
        {data && (
          <span className="text-emerald-600 dark:text-emerald-400">
            API status: {data.status} (as of {data.time_utc})
          </span>
        )}
      </div>
    </div>
  );
}
