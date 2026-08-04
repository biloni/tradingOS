"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useProposeOrder } from "@/lib/hooks/usePaperOrders";
import type { PaperOrderSide, PaperOrderType } from "@/lib/api/paperOrders";

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

/** Step 1 of 2 (ADR-014, principle 11) — only proposes a DRAFT order.
 * Nothing reaches Alpaca here; the OrderList's Confirm button is the
 * actual human-confirmation gate. */
export function OrderForm() {
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState<PaperOrderSide>("BUY");
  const [quantity, setQuantity] = useState("1");
  const [orderType, setOrderType] = useState<PaperOrderType>("MARKET");
  const [limitPrice, setLimitPrice] = useState("");

  const propose = useProposeOrder();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    propose.mutate(
      {
        ticker: ticker.toUpperCase(),
        side,
        quantity: Number(quantity),
        order_type: orderType,
        limit_price: orderType === "LIMIT" && limitPrice ? limitPrice : null,
      },
      {
        onSuccess: () => {
          setTicker("");
          setQuantity("1");
          setLimitPrice("");
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
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
            onChange={(e) => setSide(e.target.value as PaperOrderSide)}
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
            onChange={(e) => setOrderType(e.target.value as PaperOrderType)}
            className={SELECT_CLASSES}
          >
            <option value="MARKET">MARKET</option>
            <option value="LIMIT">LIMIT</option>
          </select>
        </Field>
        {orderType === "LIMIT" && (
          <Field label="Limit price">
            <Input
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder="0.00"
              required
            />
          </Field>
        )}
      </div>
      <ErrorBanner error={propose.error} />
      <div>
        <Button type="submit" disabled={propose.isPending}>
          {propose.isPending ? "Proposing…" : "Propose order"}
        </Button>
      </div>
    </form>
  );
}
