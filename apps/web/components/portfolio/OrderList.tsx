"use client";

import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { StatusPill } from "@/components/ui/StatusPill";
import { Button } from "@/components/ui/Button";
import { ConfirmButton } from "@/components/ui/ConfirmButton";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { useCancelOrder, useConfirmOrder, useOrders } from "@/lib/hooks/usePaperOrders";

export function OrderList({ accountId }: { accountId: string | undefined }) {
  const orders = useOrders(accountId);
  const confirm = useConfirmOrder(accountId);
  const cancel = useCancelOrder(accountId);

  if (orders.isLoading) return <LoadingSpinner label="Loading orders…" />;
  if (orders.error) return <ErrorBanner error={orders.error} />;
  if (!orders.data || orders.data.items.length === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No orders yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <ErrorBanner error={confirm.error ?? cancel.error} />
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
          {orders.data.items.map((order) => {
            const filledAvg =
              order.executions.length > 0
                ? (
                    order.executions.reduce((sum, e) => sum + Number(e.price) * Number(e.quantity), 0) /
                    order.executions.reduce((sum, e) => sum + Number(e.quantity), 0)
                  ).toFixed(2)
                : null;
            return (
              <Tr key={order.id}>
                <Td className="font-medium">{order.instrument.ticker}</Td>
                <Td>{order.side}</Td>
                <Td>{order.quantity}</Td>
                <Td>{order.order_type}</Td>
                <Td>
                  <StatusPill status={order.status} />
                </Td>
                <Td>{filledAvg ? `$${filledAvg}` : "—"}</Td>
                <Td>{new Date(order.created_at).toLocaleString()}</Td>
                <Td>
                  {order.status === "DRAFT" && (
                    <div className="flex justify-end gap-2">
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
                    </div>
                  )}
                </Td>
              </Tr>
            );
          })}
        </Tbody>
      </Table>
    </div>
  );
}
