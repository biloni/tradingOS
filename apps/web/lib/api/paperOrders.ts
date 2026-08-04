import { apiGet, apiPost } from "./client";

export type PaperOrderSide = "BUY" | "SELL";
export type PaperOrderType = "MARKET" | "LIMIT";
export type PaperOrderStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "FILLED"
  | "PARTIALLY_FILLED"
  | "CANCELED"
  | "REJECTED";

export type PaperOrder = {
  id: number;
  portfolio_id: number;
  ticker: string;
  side: PaperOrderSide;
  quantity: number;
  filled_quantity: number;
  order_type: PaperOrderType;
  limit_price: string | null;
  status: PaperOrderStatus;
  broker_order_id: string | null;
  filled_avg_price: string | null;
  filled_at: string | null;
  submitted_at: string | null;
  created_at: string;
};

export type ProposeOrderInput = {
  ticker: string;
  side: PaperOrderSide;
  quantity: number;
  order_type: PaperOrderType;
  limit_price?: string | null;
};

export function proposeOrder(input: ProposeOrderInput): Promise<PaperOrder> {
  return apiPost<PaperOrder>("/api/v1/paper-orders", input);
}

export function confirmOrder(id: number): Promise<PaperOrder> {
  return apiPost<PaperOrder>(`/api/v1/paper-orders/${id}/confirm`);
}

export function refreshOrder(id: number): Promise<PaperOrder> {
  return apiPost<PaperOrder>(`/api/v1/paper-orders/${id}/refresh`);
}

export function cancelOrder(id: number): Promise<PaperOrder> {
  return apiPost<PaperOrder>(`/api/v1/paper-orders/${id}/cancel`);
}

export function listOrders(): Promise<PaperOrder[]> {
  return apiGet<PaperOrder[]>("/api/v1/paper-orders");
}

export function getOrder(id: number): Promise<PaperOrder> {
  return apiGet<PaperOrder>(`/api/v1/paper-orders/${id}`);
}
