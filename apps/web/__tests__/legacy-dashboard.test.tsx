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

describe("LegacyDashboardPage", () => {
  beforeEach(() => {
    mockFetchByUrl({
      "/health": { status: "ok", time_utc: "2026-08-03T00:00:00+00:00" },
      "/api/v1/portfolio": {
        cash_usd: "9245.080000",
        positions: [{ ticker: "SPY", quantity: 1, avg_entry_price: "754.920000", current_price: "747.030000", market_value: "747.030000", unrealized_pl: "-7.890000" }],
        total_market_value: "747.030000",
        total_equity: "9992.110000",
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
      expect(screen.getByText("$9,992.11")).toBeInTheDocument();
    });
    expect(screen.getByText("$9,245.08")).toBeInTheDocument();
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
