"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api/health";
import { usePortfolio } from "@/lib/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";

const QUICK_LINKS = [
  {
    href: "/symbols",
    label: "Symbols & Charts",
    description: "Browse tracked symbols and price/indicator history.",
  },
  {
    href: "/portfolio",
    label: "Paper Portfolio",
    description: "Holdings, reconciliation, and the propose→confirm order flow.",
  },
  {
    href: "/ask",
    label: "Ask",
    description: "Natural-language questions grounded in the deterministic data model.",
  },
  {
    href: "/backtests",
    label: "Backtests",
    description: "Run a historical replay of the scoring engine.",
  },
  {
    href: "/strategy-versions",
    label: "Strategy Versions",
    description: "Propose, compare, and approve scoring-config changes.",
  },
];

function formatUsd(value: string): string {
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">{label}</div>
      <div className="text-xl font-semibold text-black dark:text-zinc-50">{value}</div>
    </div>
  );
}

export default function DashboardPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });
  const portfolio = usePortfolio();

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Dashboard
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Decision-support for 2&ndash;10 day swing trades. Research and paper-trading mode
          only &mdash; no live orders are placed.
        </p>
      </div>

      <div
        data-testid="api-status"
        className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-900"
      >
        {health.isLoading && <span className="text-zinc-500">Checking API status&hellip;</span>}
        {health.error && (
          <span className="text-red-600 dark:text-red-400">
            API unreachable: {(health.error as Error).message}
          </span>
        )}
        {health.data && (
          <span className="text-emerald-600 dark:text-emerald-400">
            API status: {health.data.status} (as of {health.data.time_utc})
          </span>
        )}
      </div>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Portfolio snapshot
        </h2>
        {portfolio.isLoading && <LoadingSpinner label="Loading portfolio…" />}
        {portfolio.error && <ErrorBanner error={portfolio.error} />}
        {portfolio.data && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Metric label="Cash" value={formatUsd(portfolio.data.cash_usd)} />
            <Metric label="Positions" value={String(portfolio.data.positions.length)} />
            <Metric label="Total equity" value={formatUsd(portfolio.data.total_equity)} />
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {QUICK_LINKS.map((link) => (
          <Link key={link.href} href={link.href}>
            <Card className="h-full transition-colors hover:border-zinc-400 dark:hover:border-zinc-600">
              <h3 className="font-medium text-black dark:text-zinc-50">{link.label}</h3>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{link.description}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
