"use client";

import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { usePortfolio, useReconciliation } from "@/lib/hooks/usePortfolio";
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
  const portfolio = usePortfolio();
  const reconciliation = useReconciliation();

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Portfolio
      </h1>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Holdings</h2>
        {portfolio.isLoading && <LoadingSpinner label="Loading portfolio…" />}
        {portfolio.error && <ErrorBanner error={portfolio.error} />}
        {portfolio.data && (
          <>
            <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">Cash</div>
                <div className="text-xl font-semibold text-black dark:text-zinc-50">
                  {formatUsd(portfolio.data.cash_usd)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
                  Market value
                </div>
                <div className="text-xl font-semibold text-black dark:text-zinc-50">
                  {formatUsd(portfolio.data.total_market_value)}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-zinc-500 dark:text-zinc-400">
                  Total equity
                </div>
                <div className="text-xl font-semibold text-black dark:text-zinc-50">
                  {formatUsd(portfolio.data.total_equity)}
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
                    <Th>Avg entry</Th>
                    <Th>Current</Th>
                    <Th>Market value</Th>
                    <Th>Unrealized P&amp;L</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {portfolio.data.positions.map((position) => (
                    <Tr key={position.ticker}>
                      <Td className="font-medium">{position.ticker}</Td>
                      <Td>{position.quantity}</Td>
                      <Td>{formatUsd(position.avg_entry_price)}</Td>
                      <Td>{formatUsd(position.current_price)}</Td>
                      <Td>{formatUsd(position.market_value)}</Td>
                      <Td
                        className={
                          Number(position.unrealized_pl ?? 0) < 0
                            ? "text-red-600 dark:text-red-400"
                            : "text-emerald-600 dark:text-emerald-400"
                        }
                      >
                        {formatUsd(position.unrealized_pl)}
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
        <OrderForm />
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Orders</h2>
        <OrderList />
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">Reconciliation</h2>
        {reconciliation.isLoading && <LoadingSpinner label="Loading reconciliation…" />}
        {reconciliation.error && <ErrorBanner error={reconciliation.error} />}
        {reconciliation.data && reconciliation.data.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No positions to reconcile.</p>
        )}
        {reconciliation.data && reconciliation.data.length > 0 && (
          <Table>
            <Thead>
              <Tr>
                <Th>Ticker</Th>
                <Th>Our qty</Th>
                <Th>Alpaca qty</Th>
                <Th>Discrepancy</Th>
              </Tr>
            </Thead>
            <Tbody>
              {reconciliation.data.map((row) => (
                <Tr key={row.ticker}>
                  <Td className="font-medium">{row.ticker}</Td>
                  <Td>{row.our_quantity}</Td>
                  <Td>{row.alpaca_quantity}</Td>
                  <Td
                    className={
                      Number(row.discrepancy) !== 0
                        ? "font-semibold text-red-600 dark:text-red-400"
                        : ""
                    }
                  >
                    {row.discrepancy}
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
