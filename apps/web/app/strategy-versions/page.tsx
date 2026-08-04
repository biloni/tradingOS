"use client";

import Link from "next/link";
import { useState, type FormEvent, type ReactNode } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { StatusPill } from "@/components/ui/StatusPill";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { useProposeStrategyVersion, useStrategyVersions } from "@/lib/hooks/useStrategyVersions";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  );
}

const PROPOSE_ERROR_MESSAGES = {
  422: "The submitted weights/RSI band didn't pass validation — check that rsi_bullish_low is less than rsi_bullish_high.",
};

export default function StrategyVersionsPage() {
  const versions = useStrategyVersions();
  const propose = useProposeStrategyVersion();

  const [name, setName] = useState("");
  const [trend, setTrend] = useState("1.0");
  const [momentum, setMomentum] = useState("1.0");
  const [macd, setMacd] = useState("1.0");
  const [bollinger, setBollinger] = useState("1.0");
  const [rsiLow, setRsiLow] = useState("50");
  const [rsiHigh, setRsiHigh] = useState("70");
  const [rsiOversold, setRsiOversold] = useState("30");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    propose.mutate(
      {
        name,
        config: {
          weights: {
            trend: Number(trend),
            momentum: Number(momentum),
            macd: Number(macd),
            bollinger: Number(bollinger),
          },
          rsi_bullish_low: Number(rsiLow),
          rsi_bullish_high: Number(rsiHigh),
          rsi_oversold: Number(rsiOversold),
        },
      },
      { onSuccess: () => setName("") },
    );
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        Strategy Versions
      </h1>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">
          Propose a candidate
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Tighter RSI band"
              required
            />
          </Field>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Field label="Trend weight">
              <Input value={trend} onChange={(e) => setTrend(e.target.value)} />
            </Field>
            <Field label="Momentum weight">
              <Input value={momentum} onChange={(e) => setMomentum(e.target.value)} />
            </Field>
            <Field label="MACD weight">
              <Input value={macd} onChange={(e) => setMacd(e.target.value)} />
            </Field>
            <Field label="Bollinger weight">
              <Input value={bollinger} onChange={(e) => setBollinger(e.target.value)} />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Field label="RSI bullish low">
              <Input value={rsiLow} onChange={(e) => setRsiLow(e.target.value)} />
            </Field>
            <Field label="RSI bullish high">
              <Input value={rsiHigh} onChange={(e) => setRsiHigh(e.target.value)} />
            </Field>
            <Field label="RSI oversold">
              <Input value={rsiOversold} onChange={(e) => setRsiOversold(e.target.value)} />
            </Field>
          </div>
          <ErrorBanner error={propose.error} messages={PROPOSE_ERROR_MESSAGES} />
          <div>
            <Button type="submit" disabled={propose.isPending}>
              {propose.isPending ? "Proposing…" : "Propose"}
            </Button>
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="mb-4 text-lg font-medium text-black dark:text-zinc-50">All versions</h2>
        {versions.isLoading && <LoadingSpinner label="Loading strategy versions…" />}
        {versions.error && <ErrorBanner error={versions.error} />}
        {versions.data && (
          <Table>
            <Thead>
              <Tr>
                <Th>Name</Th>
                <Th>Status</Th>
                <Th>Decided</Th>
                <Th>Created</Th>
              </Tr>
            </Thead>
            <Tbody>
              {versions.data.map((version) => (
                <Tr key={version.id}>
                  <Td>
                    <Link
                      href={`/strategy-versions/${version.id}`}
                      className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {version.name}
                    </Link>
                  </Td>
                  <Td>
                    <StatusPill status={version.status} />
                  </Td>
                  <Td>
                    {version.decided_at ? new Date(version.decided_at).toLocaleString() : "—"}
                  </Td>
                  <Td>{new Date(version.created_at).toLocaleString()}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
