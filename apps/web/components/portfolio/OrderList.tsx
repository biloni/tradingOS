"use client";

import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { StatusPill } from "@/components/ui/StatusPill";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  useCancelOrder,
  useConfirmOrder,
  usePaperOrders,
  useRefreshOrder,
} from "@/lib/hooks/usePaperOrders";

const NON_TERMINAL = new Set(["SUBMITTED", "PARTIALLY_FILLED"]);

export function OrderList() {
  const orders = usePaperOrders();
  const confirm = useConfirmOrder();
  const cancel = useCancelOrder();
  const refresh = useRefreshOrder();

  if (orders.isLoading) return <LoadingSpinner label="Loading orders…" />;
  if (orders.error) return <ErrorBanner error={orders.error} />;
  if (!orders.data || orders.data.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No paper orders yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <ErrorBanner error={confirm.error ?? cancel.error ?? refresh.error} />
      <Table>
        <Thead>
          <Tr>
            <Th>Ticker</Th>
            <Th>Side</Th>
            <Th>Qty</Th>
            <Th>Type</Th>
            <Th>Status</Th>
            <Th>Filled avg</Th>
            <Th>Created</Th>
            <Th />
          </Tr>
        </Thead>
        <Tbody>
          {orders.data.map((order) => (
            <Tr key={order.id}>
              <Td className="font-medium">{order.ticker}</Td>
              <Td>{order.side}</Td>
              <Td>
                {order.filled_quantity}/{order.quantity}
              </Td>
              <Td>{order.order_type}</Td>
              <Td>
                <StatusPill status={order.status} />
              </Td>
              <Td>
                {order.filled_avg_price ? `$${Number(order.filled_avg_price).toFixed(2)}` : "—"}
              </Td>
              <Td>{new Date(order.created_at).toLocaleString()}</Td>
              <Td>
                <div className="flex justify-end gap-2">
                  {order.status === "DRAFT" && (
                    <>
                      <ConfirmButton
                        label="Confirm"
                        onConfirm={() => confirm.mutate(order.id)}
                        disabled={confirm.isPending}
                      />
                      <Button
                        variant="ghost"
                        onClick={() => cancel.mutate(order.id)}
                        disabled={cancel.isPending}
                      >
                        Cancel
                      </Button>
                    </>
                  )}
                  {NON_TERMINAL.has(order.status) && (
                    <Button
                      variant="secondary"
                      onClick={() => refresh.mutate(order.id)}
                      disabled={refresh.isPending}
                    >
                      Refresh
                    </Button>
                  )}
                </div>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </div>
  );
}
