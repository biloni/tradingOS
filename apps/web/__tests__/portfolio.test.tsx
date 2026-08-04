import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioPage from "@/app/portfolio/page";
import type { PaperOrder } from "@/lib/api/paperOrders";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const PORTFOLIO_SNAPSHOT = {
  cash_usd: "10000.000000",
  positions: [],
  total_market_value: "0.000000",
  total_equity: "10000.000000",
};

/** Mimics the real backend closely enough for these tests: propose creates a
 * DRAFT order in `orders`, confirm flips it to SUBMITTED — so a refetch after
 * each mutation (driven by TanStack Query invalidation) reflects the change,
 * the same way it does against the real API. */
function mockFetch({ proposeStatus = 200 }: { proposeStatus?: number } = {}) {
  let orders: PaperOrder[] = [];
  let nextId = 1;

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";

      if (path === "/api/v1/portfolio" && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(PORTFOLIO_SNAPSHOT),
        });
      }
      if (path === "/api/v1/portfolio/reconciliation" && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) });
      }
      if (path === "/api/v1/paper-orders" && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(orders) });
      }
      if (path === "/api/v1/paper-orders" && method === "POST") {
        if (proposeStatus !== 200) {
          return Promise.resolve({
            ok: false,
            status: proposeStatus,
            json: () => Promise.resolve({ detail: "Unknown ticker." }),
          });
        }
        const body = JSON.parse(init!.body as string);
        const order: PaperOrder = {
          id: nextId++,
          portfolio_id: 1,
          ticker: body.ticker,
          side: body.side,
          quantity: body.quantity,
          filled_quantity: 0,
          order_type: body.order_type,
          limit_price: body.limit_price ?? null,
          status: "DRAFT",
          broker_order_id: null,
          filled_avg_price: null,
          filled_at: null,
          submitted_at: null,
          created_at: "2026-08-01T12:00:00+00:00",
        };
        orders = [...orders, order];
        return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(order) });
      }
      const confirmMatch = path.match(/^\/api\/v1\/paper-orders\/(\d+)\/confirm$/);
      if (confirmMatch && method === "POST") {
        const id = Number(confirmMatch[1]);
        orders = orders.map((o) => (o.id === id ? { ...o, status: "SUBMITTED" as const } : o));
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

describe("PortfolioPage — paper order propose→confirm flow", () => {
  beforeEach(() => {
    mockFetch();
  });

  it("proposes a DRAFT order and lists it with Confirm/Cancel actions", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<PortfolioPage />);

    await waitFor(() => expect(screen.getByText("No paper orders yet.")).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText("AAPL"), "aapl");
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
    await user.click(screen.getByRole("button", { name: "Propose order" }));
    await waitFor(() => expect(screen.getByText("MSFT")).toBeInTheDocument());

    const row = screen.getByText("MSFT").closest("tr")!;
    await user.click(within(row).getByRole("button", { name: "Confirm" }));

    // First click reveals the gate, not the mutation — status must still be DRAFT.
    expect(within(row).getByText("Are you sure?")).toBeInTheDocument();
    expect(within(row).getByText("DRAFT")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(within(row).getByText("SUBMITTED")).toBeInTheDocument());
  });

  it("surfaces a propose error via ErrorBanner without adding a row", async () => {
    mockFetch({ proposeStatus: 400 });
    const user = userEvent.setup();
    renderWithQueryClient(<PortfolioPage />);

    await user.type(screen.getByPlaceholderText("AAPL"), "zzzz");
    await user.click(screen.getByRole("button", { name: "Propose order" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The request couldn't be completed as sent.",
      ),
    );
    expect(screen.getByText("No paper orders yet.")).toBeInTheDocument();
  });
});
