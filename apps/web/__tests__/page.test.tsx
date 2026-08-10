import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MorningDashboardPage from "@/app/page";
import type { DashboardResponse, MorningPlanItem } from "@/lib/api/morningPlan";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const ACCOUNT_ID = "acc-1";

function emptySections() {
  return (
    [
      "ACT_NOW",
      "APPROVAL_REQUIRED",
      "BUY_AND_HOLD",
      "TACTICAL_TRADES",
      "UPCOMING_EVENTS",
      "WATCH_AND_AVOID",
      "DATA_PROBLEMS",
    ] as const
  ).map((key, i) => ({ section_key: key, display_order: i, items: [] as MorningPlanItem[] }));
}

function baseDashboard(overrides: Partial<DashboardResponse["top_status"]> = {}): DashboardResponse {
  return {
    top_status: {
      market_date: "2026-08-10",
      is_trading_day: true,
      market_closed_reason: null,
      countdown_to_open_seconds: 3600,
      plan_status: "COMPLETE",
      plan_version_id: "version-1",
      plan_version_label: "FINAL",
      generated_at: "2026-08-10T13:10:00Z",
      evidence_cutoff: "2026-08-10T13:08:00Z",
      provider_broker_status: "OK",
      regime_classification: "CALM",
      vix_proxy_level: null,
      vix_percentile: null,
      total_equity: "100000.00",
      cash: "20000.00",
      exposure_pct: "45.00",
      risk_budget_pct: "10.00",
      operating_mode: "PAPER_MANUAL_APPROVAL",
      kill_switch_active: false,
      ...overrides,
    },
    version: {
      id: "version-1",
      morning_plan_run_id: "run-1",
      plan_date: "2026-08-10",
      version_label: "FINAL",
      version_number: 1,
      evidence_cutoff: "2026-08-10T13:08:00Z",
      generated_at: "2026-08-10T13:10:00Z",
      completeness_status: "COMPLETE",
      sections: emptySections(),
      quality_checks: [],
      delivery_events: [],
    },
  };
}

function mockFetch(dashboard: DashboardResponse) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/morning-plan/dashboard")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(dashboard) });
      }
      if (url.includes("/api/v1/portfolio/accounts")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve([
              { id: ACCOUNT_ID, account_type: "MANUAL", name: "Test", base_currency: "USD", is_active: true },
            ]),
        });
      }
      if (url.includes("/api/v1/performance/portfolio/")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              as_of: "2026-08-10",
              equity: "100000.00",
              cash: "20000.00",
              daily_return_pct: "0.42",
              weekly_return_pct: "-1.10",
              realized_pnl: "500.00",
              unrealized_pnl: "0.00",
              drawdown: { max_drawdown_pct: "-3.20", peak_index: null, trough_index: null, recovery_index: null, recovery_periods: null },
              gross_exposure_pct: "45.00",
              sample_size_days: 20,
            }),
        });
      }
      return Promise.reject(new Error(`No mock response for ${url}`));
    }),
  );
}

describe("MorningDashboardPage", () => {
  beforeEach(() => {
    mockFetch(baseDashboard());
  });

  it("renders the Morning Decision Dashboard heading", async () => {
    renderWithQueryClient(<MorningDashboardPage />);
    await waitFor(() => expect(screen.getByText("Morning Decision Dashboard")).toBeInTheDocument());
  });

  it("renders the status strip with real plan/mode/regime data", async () => {
    renderWithQueryClient(<MorningDashboardPage />);
    const status = await screen.findByRole("region", { name: "Status" });
    expect(within(status).getByText("2026-08-10")).toBeInTheDocument();
    expect(within(status).getByText("COMPLETE")).toBeInTheDocument();
    expect(within(status).getByText("CALM")).toBeInTheDocument();
    expect(within(status).getByText("PAPER MANUAL APPROVAL")).toBeInTheDocument();
    expect(within(status).getByText(/Kill switch off/)).toBeInTheDocument();
  });

  it("renders the portfolio strip with equity, cash, and day/week P&L", async () => {
    renderWithQueryClient(<MorningDashboardPage />);
    const portfolio = await screen.findByRole("region", { name: "Portfolio" });
    expect(within(portfolio).getByText("$100,000")).toBeInTheDocument();
    expect(within(portfolio).getByText("$20,000")).toBeInTheDocument();
    await waitFor(() => expect(within(portfolio).getByText("+0.42%")).toBeInTheDocument());
    expect(within(portfolio).getByText("-1.10%")).toBeInTheDocument();
  });

  it("renders every required section in the Revision Prompt 15 order", async () => {
    renderWithQueryClient(<MorningDashboardPage />);
    await screen.findByText("Morning Decision Dashboard");
    const expected = [
      "Act Now",
      "Approval Required",
      "Buy and Hold",
      "Tactical Earnings",
      "Existing Positions",
      "Upcoming Events",
      "Watch/Avoid",
      "Data and Job Health",
    ];
    await waitFor(() => {
      const headings = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
      for (const label of expected) {
        expect(headings.some((h) => h?.startsWith(label))).toBe(true);
      }
    });
  });

  it("shows the incomplete-plan banner as an alert when the plan is INCOMPLETE", async () => {
    const dashboard = baseDashboard({ plan_status: "COMPLETE" });
    dashboard.version!.completeness_status = "INCOMPLETE";
    dashboard.version!.quality_checks = [
      { check_name: "stale_recommendation:AAPL:TACTICAL", passed: false, detail: "AAPL is stale." },
    ];
    mockFetch(dashboard);
    renderWithQueryClient(<MorningDashboardPage />);
    const alert = await screen.findByText("This plan is INCOMPLETE");
    expect(alert.closest('[role="alert"]')).not.toBeNull();
    // Appears twice by design: once in the top completeness banner, once
    // in the "Data and Job Health" section's own failed-checks list.
    expect(screen.getAllByText("AAPL is stale.").length).toBeGreaterThanOrEqual(1);
  });

  it("shows a market-closed state instead of the plan sections", async () => {
    const dashboard = baseDashboard({
      plan_status: "MARKET_CLOSED",
      is_trading_day: false,
      market_closed_reason: "Weekend",
    });
    dashboard.version = null;
    mockFetch(dashboard);
    renderWithQueryClient(<MorningDashboardPage />);
    await waitFor(() => expect(screen.getByText("Market is closed")).toBeInTheDocument());
    expect(screen.queryByText("Act Now")).not.toBeInTheDocument();
  });

  it("shows an honest empty state when no plan has been generated yet", async () => {
    const dashboard = baseDashboard({ plan_status: "INCOMPLETE" });
    dashboard.version = null;
    mockFetch(dashboard);
    renderWithQueryClient(<MorningDashboardPage />);
    await waitFor(() =>
      expect(screen.getByText("No plan has been generated yet today")).toBeInTheDocument(),
    );
  });
});
