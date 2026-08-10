import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import OrderApprovalPage from "@/app/approvals/[id]/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "approval-1" }),
}));

function renderWithQueryClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <OrderApprovalPage />
    </QueryClientProvider>,
  );
}

const BOUND_FIELDS = {
  account_id: "acc-1",
  instrument_id: "inst-1",
  side: "BUY",
  quantity: "5.00000000",
  order_type: "LIMIT",
  limit_price: "150.000000",
  stop_price: null,
  time_in_force: "DAY",
  outside_hours: false,
  attached_legs: {},
  max_notional: null,
  recommendation_version_id: "rv-1",
  quote_price_at_approval: "149.500000",
};

function approvalFixture(overrides: Partial<{ status: string }> = {}) {
  return {
    id: "approval-1",
    order_proposal_version_id: "opv-1",
    approved_by: null,
    requested_at: "2026-08-10T10:00:00-07:00",
    decided_at: null,
    expires_at: "2026-08-10T10:30:00-07:00",
    status: "PENDING",
    integrity_hash: "abcdef0123456789abcdef0123456789",
    bound_fields: BOUND_FIELDS,
    ...overrides,
  };
}

function mockFetch({
  approval,
  canSubmitOrders = true,
  refresh,
  approveStatus = 200,
  submitStatus = 200,
}: {
  approval: ReturnType<typeof approvalFixture>;
  canSubmitOrders?: boolean;
  refresh?: Record<string, unknown>;
  approveStatus?: number;
  submitStatus?: number;
}) {
  let current = approval;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";

      if (path === "/api/v1/order-approvals/approval-1" && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(current) });
      }
      if (path === "/api/v1/settings/operating-mode" && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              mode: "PAPER_MANUAL_APPROVAL",
              environment_label: "PAPER",
              can_submit_orders: canSubmitOrders,
            }),
        });
      }
      if (path === "/api/v1/order-approvals/approval-1/refresh" && method === "GET") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve(
              refresh ?? {
                quote_price: "149.60",
                quote_observed_at: "2026-08-10T10:05:00-07:00",
                buying_power: "10000.00",
                open_position_quantity: "0",
                open_order_count: 0,
                is_trading_day: true,
                market_closed_reason: null,
                upcoming_earnings_report_date: null,
                requires_reapproval: false,
                reason: null,
              },
            ),
        });
      }
      if (path === "/api/v1/order-approvals/approval-1/approve" && method === "POST") {
        if (approveStatus !== 200) {
          return Promise.resolve({
            ok: false,
            status: approveStatus,
            json: () => Promise.resolve({ detail: "Cannot approve." }),
          });
        }
        current = { ...current, status: "APPROVED" };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(current) });
      }
      if (path === "/api/v1/order-approvals/approval-1/submit" && method === "POST") {
        if (submitStatus !== 200) {
          return Promise.resolve({
            ok: false,
            status: submitStatus,
            json: () => Promise.resolve({ detail: "RESEARCH_ONLY cannot create broker orders" }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              attempt: {
                id: "attempt-1",
                order_approval_id: "approval-1",
                attempted_at: "2026-08-10T10:06:00-07:00",
                environment_label: "PAPER",
                outcome: "SUCCESS",
                idempotency_key: null,
                detail: null,
                resulting_order_id: "order-1",
              },
              order_id: "order-1",
              order_status: "SUBMITTED",
              invalidated: false,
              invalidation_reason: null,
              used_native_bracket: true,
              disclosure: null,
              stop_loss_order_id: null,
              take_profit_order_id: null,
            }),
        });
      }
      return Promise.reject(new Error(`No mock handler for ${method} ${path}`));
    }),
  );
}

describe("OrderApprovalPage — final immutable summary and deliberate confirmation", () => {
  it("renders the bound fields as an immutable summary", async () => {
    mockFetch({ approval: approvalFixture() });
    renderWithQueryClient();

    await waitFor(() => expect(screen.getByText("PENDING")).toBeInTheDocument());
    expect(screen.getByText("BUY")).toBeInTheDocument();
    expect(screen.getByText("5.00000000")).toBeInTheDocument();
    expect(screen.getByText("150.000000")).toBeInTheDocument();
  });

  it("requires a second explicit click before approving", async () => {
    mockFetch({ approval: approvalFixture() });
    const user = userEvent.setup();
    renderWithQueryClient();

    await waitFor(() => expect(screen.getByText("PENDING")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Approve this order" }));

    // First click reveals the gate, not the mutation.
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
    expect(screen.getByText("PENDING")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Yes, approve exactly as shown above" }));

    await waitFor(() => expect(screen.getByText("APPROVED")).toBeInTheDocument());
  });

  it("surfaces a denial from the server without silently retrying", async () => {
    mockFetch({ approval: approvalFixture(), approveStatus: 400 });
    const user = userEvent.setup();
    renderWithQueryClient();

    await waitFor(() => expect(screen.getByText("PENDING")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Approve this order" }));
    await user.click(screen.getByRole("button", { name: "Yes, approve exactly as shown above" }));

    await waitFor(() =>
      expect(
        screen.getByText("This approval can no longer be approved (likely expired)."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("PENDING")).toBeInTheDocument();
  });

  it("blocks submission upfront when the operating mode cannot submit orders, without a false confirm step", async () => {
    mockFetch({ approval: approvalFixture({ status: "APPROVED" }), canSubmitOrders: false });
    renderWithQueryClient();

    await waitFor(() =>
      expect(screen.getByText("Submission is not available right now")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Submit to broker" })).not.toBeInTheDocument();
  });

  it("shows a hard pre-submission block (e.g. non-broker-backed account) with its real reason", async () => {
    mockFetch({
      approval: approvalFixture({ status: "APPROVED" }),
      refresh: {
        quote_price: "149.60",
        quote_observed_at: "2026-08-10T10:05:00-07:00",
        buying_power: "10000.00",
        open_position_quantity: "0",
        open_order_count: 0,
        is_trading_day: true,
        market_closed_reason: null,
        upcoming_earnings_report_date: null,
        requires_reapproval: true,
        reason: "Blocked: account_type=MANUAL is not a broker-backed account.",
      },
    });
    renderWithQueryClient();

    await waitFor(() =>
      expect(
        screen.getByText(
          "This order cannot be submitted: Blocked: account_type=MANUAL is not a broker-backed account..",
        ),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Submit to broker" })).not.toBeInTheDocument();
  });

  it("requires a second explicit click before submitting, then shows broker status", async () => {
    mockFetch({ approval: approvalFixture({ status: "APPROVED" }) });
    const user = userEvent.setup();
    renderWithQueryClient();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Submit to broker" })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Submit to broker" }));

    expect(screen.getByText("Are you sure?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Yes, submit exactly as shown above" }));

    await waitFor(() => expect(screen.getByText("SUCCESS")).toBeInTheDocument());
    expect(screen.getByText("SUBMITTED")).toBeInTheDocument();
  });
});
