"use client";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { useAccountDetail, useReconciliationRuns } from "@/lib/hooks/usePortfolio";
import { useDefaultAccount } from "@/lib/hooks/useAccounts";
import { OrderForm } from "@/components/portfolio/OrderForm";
import { OrderList } from "@/components/portfolio/OrderList";

function formatUsd(value: string | null): string {
  if (value === null) return "—";
  return `$${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function PortfolioPage() {
  const { data: account } = useDefaultAccount();
  const portfolio = useAccountDetail(account?.id);
  const reconciliation = useReconciliationRuns(account?.id);
  const latestRun = reconciliation.data?.[0];

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Portfolio
      </h1>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Holdings — {account?.name ?? "…"}
        </h2>
        {portfolio.isLoading && <LoadingSpinner label="Loading portfolio…" />}
        {portfolio.error && <ErrorBanner error={portfolio.error} />}
        {portfolio.data && (
          <>
            <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Cash</div>
                <div className="text-xl font-semibold text-black dark:text-zinc-50">
                  {formatUsd(portfolio.data.cash.cash)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
                  Gross exposure
                </div>
                <div className="text-xl font-semibold text-black dark:text-zinc-50">
                  {portfolio.data.latest_risk_snapshot?.gross_exposure_pct
                    ? `${portfolio.data.latest_risk_snapshot.gross_exposure_pct}%`
                    : "no risk snapshot yet"}
                </div>
              </div>
            </div>
            {portfolio.data.positions.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">No open positions.</p>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Ticker</Th>
                    <Th>Qty</Th>
                    <Th>Avg cost</Th>
                    <Th>Market value</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {portfolio.data.positions.map((position) => (
                    <Tr key={position.instrument.id}>
                      <Td className="font-medium">{position.instrument.ticker}</Td>
                      <Td>{position.quantity}</Td>
                      <Td>{formatUsd(position.avg_cost)}</Td>
                      <Td>
                        {position.market_value !== null
                          ? formatUsd(position.market_value)
                          : "not computed on this screen — see Symbols for live quotes"}
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Propose a paper order
        </h2>
        <OrderForm accountId={account?.id} />
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Orders</h2>
        <OrderList accountId={account?.id} />
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Reconciliation</h2>
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
          A discrete, timestamped comparison against broker-reported positions — there is no live
          background diff. Trigger a new run from the account detail API to refresh this.
        </p>
        {reconciliation.isLoading && <LoadingSpinner label="Loading reconciliation…" />}
        {reconciliation.error && <ErrorBanner error={reconciliation.error} />}
        {reconciliation.data && reconciliation.data.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No reconciliation run has ever been triggered for this account.
          </p>
        )}
        {latestRun && (
          <>
            <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
              Latest run: {new Date(latestRun.as_of).toLocaleString()} — overall{" "}
              {latestRun.overall_status}
            </p>
            {latestRun.lines.length === 0 ? (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">No positions to reconcile.</p>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Ticker</Th>
                    <Th>Internal qty</Th>
                    <Th>Broker-reported qty</Th>
                    <Th>Status</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {latestRun.lines.map((line) => (
                    <Tr key={line.instrument.id}>
                      <Td className="font-medium">{line.instrument.ticker}</Td>
                      <Td>{line.internal_quantity}</Td>
                      <Td>{line.broker_reported_quantity ?? "—"}</Td>
                      <Td
                        className={
                          line.status !== "MATCHED"
                            ? "font-semibold text-red-600 dark:text-red-400"
                            : ""
                        }
                      >
                        {line.status}
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
