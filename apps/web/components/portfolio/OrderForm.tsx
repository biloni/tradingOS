"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useSymbols } from "@/lib/hooks/useSymbols";
import { useCreateOrder } from "@/lib/hooks/usePaperOrders";
import type { OrderSide, OrderType } from "@/lib/api/paperOrders";
import { ApiError } from "@/lib/api/client";

const SELECT_CLASSES =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-black focus:border-black focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:border-zinc-50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  );
}

/**
 * Step 1 of 2 (ADR-014, principle 11) — only proposes a DRAFT order.
 * Nothing reaches a broker here; OrderList's Confirm button is the
 * actual human-confirmation gate. Price is always required (not only
 * for LIMIT orders): confirming a `MANUAL`-account order fills it
 * immediately at this price — there is no broker to derive one from
 * (`routers/orders.py::confirm_order()` 422s a manual fill with no
 * price), so this form never lets a user reach that error at confirm
 * time instead of here.
 */
export function OrderForm({ accountId }: { accountId: string | undefined }) {
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<OrderSide>("BUY");
  const [quantity, setQuantity] = useState("1");
  const [orderType, setOrderType] = useState<OrderType>("MARKET");
  const [price, setPrice] = useState("");

  const symbols = useSymbols();
  const create = useCreateOrder(accountId);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!accountId) return;
    const instrument = symbols.data?.find((s) => s.ticker === ticker.toUpperCase());
    if (!instrument) return;
    create.mutate(
      {
        accountId,
        instrumentId: instrument.id,
        side,
        orderType,
        quantity,
        limitPrice: price || null,
      },
      {
        onSuccess: () => {
          setTicker("");
          setQuantity("1");
          setPrice("");
        },
      },
    );
  }

  const knownTicker = symbols.data?.some((s) => s.ticker === ticker.toUpperCase()) ?? false;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <Field label="Ticker">
          <Input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="AAPL"
            required
          />
        </Field>
        <Field label="Side">
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as OrderSide)}
            className={SELECT_CLASSES}
          >
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </Field>
        <Field label="Quantity">
          <Input
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
        </Field>
        <Field label="Order type">
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as OrderType)}
            className={SELECT_CLASSES}
          >
            <option value="MARKET">MARKET</option>
            <option value="LIMIT">LIMIT</option>
          </select>
        </Field>
        <Field label="Price (used to record the fill on confirm)">
          <Input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="0.00"
            required
          />
        </Field>
      </div>
      {ticker && !knownTicker && !symbols.isLoading && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          &quot;{ticker.toUpperCase()}&quot; isn&apos;t a known symbol.
        </p>
      )}
      <ErrorBanner
        error={create.error}
        messages={
          create.error instanceof ApiError
            ? { 422: "Unknown account or symbol, or a price is required to confirm this order." }
            : undefined
        }
      />
      <div>
        <Button type="submit" disabled={create.isPending || !accountId || !knownTicker}>
          {create.isPending ? "Proposing…" : "Propose order"}
        </Button>
      </div>
    </form>
  );
}
