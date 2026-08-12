import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ApprovalQueuePage from "@/app/approvals/page";

function renderWithQueryClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApprovalQueuePage />
    </QueryClientProvider>,
  );
}

function approvalFixture() {
  return {
    id: "approval-1",
    order_proposal_version_id: "opv-1",
    approved_by: null,
    requested_at: "2026-08-10T10:00:00-07:00",
    decided_at: null,
    expires_at: "2026-08-10T10:30:00-07:00",
    status: "PENDING",
    integrity_hash: "abcdef0123456789abcdef0123456789",
    bound_fields: {
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
    },
  };
}

function mockFetch(approvals: ReturnType<typeof approvalFixture>[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/order-approvals")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(approvals),
        });
      }
      return Promise.reject(new Error(`No mock response for ${url}`));
    }),
  );
}

describe("Approval Queue page", () => {
  it("renders the empty state when nothing is pending", async () => {
    mockFetch([]);
    renderWithQueryClient();
    expect(screen.getByRole("heading", { level: 1, name: "Approval Queue" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/No orders awaiting approval right now/)).toBeInTheDocument();
    });
  });

  it("lists a real pending approval, linking to its detail page", async () => {
    mockFetch([approvalFixture()]);
    renderWithQueryClient();
    await waitFor(() => {
      expect(screen.getByText("BUY")).toBeInTheDocument();
    });
    const link = screen.getByRole("link", { name: "BUY" });
    expect(link).toHaveAttribute("href", "/approvals/approval-1");
    expect(screen.getByText("5.00000000")).toBeInTheDocument();
  });
});
