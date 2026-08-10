import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/legacy-dashboard/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockFetchByUrl(responses: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const body = responses[path];
      if (body === undefined) {
        return Promise.reject(new Error(`No mock response for ${path}`));
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    }),
  );
}

const ACCOUNT_ID = "acc-1";

describe("LegacyDashboardPage", () => {
  beforeEach(() => {
    mockFetchByUrl({
      "/health": { status: "ok", time_utc: "2026-08-03T00:00:00+00:00" },
      "/api/v1/portfolio/accounts": [
        { id: ACCOUNT_ID, account_type: "MANUAL", name: "Test", base_currency: "USD", is_active: true },
      ],
      [`/api/v1/portfolio/accounts/${ACCOUNT_ID}`]: {
        account: { id: ACCOUNT_ID, account_type: "MANUAL", name: "Test", base_currency: "USD", is_active: true },
        cash: { account_id: ACCOUNT_ID, cash: "9245.080000", starting_cash: "10000.00" },
        positions: [
          {
            instrument: { id: "inst-spy", ticker: "SPY", name: "SPDR S&P 500", exchange: "NYSE", asset_type: "EQUITY", active: true },
            quantity: "1",
            avg_cost: "754.920000",
            market_value: null,
          },
        ],
        latest_risk_snapshot: null,
      },
    });
  });

  it("renders the dashboard heading and reports healthy API status", async () => {
    renderWithQueryClient(<DashboardPage />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("api-status")).toHaveTextContent("API status: ok");
    });
  });

  it("renders the portfolio snapshot", async () => {
    renderWithQueryClient(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByText("$9,245.08")).toBeInTheDocument();
    });
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("links to every other section", () => {
    renderWithQueryClient(<DashboardPage />);

    for (const label of [
      "Symbols & Charts",
      "Paper Portfolio",
      "Ask",
      "Backtests",
      "Strategy Versions",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
