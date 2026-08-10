import { apiGet, apiPost } from "./client";
import type { Instrument } from "./portfolio";

/**
 * Previously called a nonexistent `/api/v1/paper-orders*` (int-PK
 * shape from an earlier backend generation). Rewired to the real,
 * currently-shipped `/api/v1/orders` router
 * (`docs/API_CONTRACTS.md` area 6) — UUID-keyed, `instrument_id`-based.
 */
export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT";
export type OrderStatus = "DRAFT" | "SUBMITTED" | "FILLED" | "PARTIALLY_FILLED" | "CANCELED" | "REJECTED";

export type Execution = {
  id: string;
  quantity: string;
  price: string;
  executed_at: string;
};

export type Order = {
  id: string;
  account_id: string;
  instrument: Instrument;
  side: OrderSide;
  order_type: OrderType;
  time_in_force: string;
  quantity: string;
  limit_price: string | null;
  status: OrderStatus;
  submitted_at: string | null;
  filled_at: string | null;
  created_at: string;
  executions: Execution[];
};

export type CreateOrderInput = {
  accountId: string;
  instrumentId: string;
  side: OrderSide;
  orderType: OrderType;
  quantity: string;
  limitPrice: string | null;
};

/**
 * Step 1 of 2 (ADR-014) — only ever creates a `DRAFT` row. `limitPrice`
 * is required here even for a `MARKET` order against a `MANUAL`
 * account: `POST /{id}/confirm` fills a manual order immediately (there
 * is no broker to wait on) and needs a price to record that fill —
 * `services/orders.py` 422s a manual confirm with no price.
 */
export function createOrder(input: CreateOrderInput): Promise<Order> {
  return apiPost<Order>("/api/v1/orders", {
    account_id: input.accountId,
    instrument_id: input.instrumentId,
    side: input.side,
    order_type: input.orderType,
    quantity: input.quantity,
    limit_price: input.limitPrice,
  });
}

export function confirmOrder(id: string): Promise<Order> {
  return apiPost<Order>(`/api/v1/orders/${id}/confirm`);
}

export function cancelOrder(id: string): Promise<Order> {
  return apiPost<Order>(`/api/v1/orders/${id}/cancel`);
}

export function listOrders(accountId: string): Promise<{ items: Order[] }> {
  return apiGet<{ items: Order[] }>(`/api/v1/orders?account_id=${accountId}`);
}

export function getOrder(id: string): Promise<Order> {
  return apiGet<Order>(`/api/v1/orders/${id}`);
}
