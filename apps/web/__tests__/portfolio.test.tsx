import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioPage from "@/app/portfolio/page";
import type { Order } from "@/lib/api/paperOrders";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const ACCOUNT_ID = "acc-1";
const AAPL_ID = "inst-aapl";
const MSFT_ID = "inst-msft";

const ACCOUNTS = [
  { id: ACCOUNT_ID, account_type: "MANUAL", name: "Test Account", base_currency: "USD", is_active: true },
];

const ACCOUNT_DETAIL = {
  account: ACCOUNTS[0],
  cash: { account_id: ACCOUNT_ID, cash: "10000.00", starting_cash: "10000.00" },
  positions: [],
  latest_risk_snapshot: null,
};

const SYMBOLS = [
  { id: AAPL_ID, ticker: "AAPL", name: "Apple", exchange: "NASDAQ", asset_type: "EQUITY", active: true },
  { id: MSFT_ID, ticker: "MSFT", name: "Microsoft", exchange: "NASDAQ", asset_type: "EQUITY", active: true },
];

/** Mimics the real backend closely enough for these tests: creating an
 * order adds a DRAFT row to `orders`, confirm flips it to FILLED (this
 * account is MANUAL — `routers/orders.py::confirm_order()` fills a
 * manual order immediately) — so a refetch after each mutation (driven
 * by TanStack Query invalidation) reflects the change, the same way it
 * does against the real API. */
function mockFetch({ createStatus = 201 }: { createStatus?: number } = {}) {
  let orders: Order[] = [];
  let nextId = 1;

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";

      if (path === "/api/v1/portfolio/accounts" && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ACCOUNTS) });
      }
      if (path === `/api/v1/portfolio/accounts/${ACCOUNT_ID}` && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ACCOUNT_DETAIL) });
      }
      if (path === `/api/v1/portfolio/accounts/${ACCOUNT_ID}/reconciliation-runs` && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (path === "/api/v1/instruments?limit=200" && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ items: SYMBOLS, total: SYMBOLS.length, limit: 200, offset: 0 }),
        });
      }
      if (path === `/api/v1/orders?account_id=${ACCOUNT_ID}` && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ items: orders, total: orders.length, limit: 50, offset: 0 }),
        });
      }
      if (path === "/api/v1/orders" && method === "POST") {
        if (createStatus !== 201) {
          return Promise.resolve({
            ok: false,
            status: createStatus,
            json: () => Promise.resolve({ detail: "Unknown instrument_id." }),
          });
        }
        const body = JSON.parse(init!.body as string);
        const symbol = SYMBOLS.find((s) => s.id === body.instrument_id)!;
        const order: Order = {
          id: `order-${nextId++}`,
          account_id: body.account_id,
          instrument: symbol,
          side: body.side,
          order_type: body.order_type,
          time_in_force: "DAY",
          quantity: String(body.quantity),
          limit_price: body.limit_price ?? null,
          status: "DRAFT",
          submitted_at: null,
          filled_at: null,
          created_at: "2026-08-01T12:00:00+00:00",
          executions: [],
        };
        orders = [...orders, order];
        return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(order) });
      }
      const confirmMatch = path.match(/^\/api\/v1\/orders\/([^/]+)\/confirm$/);
      if (confirmMatch && method === "POST") {
        const id = confirmMatch[1];
        orders = orders.map((o) => (o.id === id ? { ...o, status: "FILLED" as const } : o));
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(orders.find((o) => o.id === id)),
        });
      }
      return Promise.reject(new Error(`No mock handler for ${method} ${path}`));
    }),
  );
}

describe("PortfolioPage — order create→confirm flow", () => {
  beforeEach(() => {
    mockFetch();
  });

  it("creates a DRAFT order and lists it with Confirm/Cancel actions", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PortfolioPage />);

    await waitFor(() => expect(screen.getByText("No orders yet.")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("AAPL"), "aapl");
    await user.type(screen.getByPlaceholderText("0.00"), "150.00");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Propose order" })).not.toBeDisabled(),
    );
    await user.click(screen.getByRole("button", { name: "Propose order" }));

    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
    expect(screen.getByText("DRAFT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("requires a second click through ConfirmButton before confirming an order", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PortfolioPage />);

    await user.type(screen.getByPlaceholderText("AAPL"), "msft");
    await user.type(screen.getByPlaceholderText("0.00"), "300.00");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Propose order" })).not.toBeDisabled(),
    );
    await user.click(screen.getByRole("button", { name: "Propose order" }));
    await waitFor(() => expect(screen.getByText("MSFT")).toBeInTheDocument());

    const row = screen.getByText("MSFT").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Confirm" }));

    // First click reveals the gate, not the mutation — status must still be DRAFT.
    expect(within(row).getByText("Are you sure?")).toBeInTheDocument();
    expect(within(row).getByText("DRAFT")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(within(row).getByText("FILLED")).toBeInTheDocument());
  });

  it("surfaces a create error via ErrorBanner without adding a row", async () => {
    mockFetch({ createStatus: 400 });
    const user = userEvent.setup();
    renderWithQueryClient(<PortfolioPage />);

    await user.type(screen.getByPlaceholderText("AAPL"), "aapl");
    await user.type(screen.getByPlaceholderText("0.00"), "150.00");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Propose order" })).not.toBeDisabled(),
    );
    await user.click(screen.getByRole("button", { name: "Propose order" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The request couldn't be completed as sent.",
      ),
    );
    expect(screen.getByText("No orders yet.")).toBeInTheDocument();
  });
});
