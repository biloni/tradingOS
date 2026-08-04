"use client";

import Link from "next/link";
import { useSymbols } from "@/lib/hooks/useSymbols";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";

export default function SymbolsPage() {
  const symbols = useSymbols();

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Symbols
      </h1>
      <Card>
        {symbols.isLoading && <LoadingSpinner label="Loading symbols…" />}
        {symbols.error && <ErrorBanner error={symbols.error} />}
        {symbols.data && (
          <Table>
            <Thead>
              <Tr>
                <Th>Ticker</Th>
                <Th>Name</Th>
                <Th>Exchange</Th>
                <Th>Type</Th>
              </Tr>
            </Thead>
            <Tbody>
              {symbols.data.map((symbol) => (
                <Tr key={symbol.id}>
                  <Td>
                    <Link
                      href={`/symbols/${symbol.ticker}`}
                      className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {symbol.ticker}
                    </Link>
                  </Td>
                  <Td>{symbol.name}</Td>
                  <Td>{symbol.exchange}</Td>
                  <Td>{symbol.asset_type}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
