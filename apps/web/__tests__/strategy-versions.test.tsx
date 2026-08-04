import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StrategyVersionDetailPage from "@/app/strategy-versions/[id]/page";
import type { BacktestRun } from "@/lib/api/backtests";
import type { StrategyVersion } from "@/lib/api/strategyVersions";

// jsdom has no real <canvas> 2D context, so lightweight-charts can't mount
// here (see CandlestickChart.tsx/EquityCurveChart.tsx comments) — mocked out
// so this suite can exercise the propose/compare/approve/reject state
// machine without depending on real chart rendering (component tests
// plan, priority 5 note: chart components get data-shape coverage only).
vi.mock("@/components/charts/EquityCurveChart", () => ({
  EquityCurveChart: () => <div data-testid="equity-curve-chart-stub" />,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
}));

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function makeBacktest(overrides: Partial<BacktestRun> = {}): BacktestRun {
  return {
    id: 1,
    strategy_version_id: 1,
    date_range_start: "2026-01-01",
    date_range_end: "2026-06-30",
    parameters: {
      entry_score_threshold: "0.60",
      exit_score_threshold: "0.40",
      max_holding_days: 20,
      position_size_pct: "10.00",
      starting_cash: "10000.00",
      benchmark_ticker: "SPY",
    },
    results_summary: {
      ending_equity: "11000.00",
      total_return_pct: "10.00",
      max_drawdown_pct: "-5.00",
      win_rate_pct: "55.00",
      num_trades: 20,
      avg_win_pct: "3.00",
      avg_loss_pct: "-1.50",
      benchmark_return_pct: "8.00",
      equity_curve: [{ as_of: "2026-01-02", equity: "10000.00" }],
      trades: [],
    },
    created_at: "2026-07-01T00:00:00+00:00",
    ...overrides,
  };
}

function mockFetch({ approveStatus = 200 }: { approveStatus?: number } = {}) {
  let version: StrategyVersion = {
    id: 1,
    name: "Candidate v2",
    config: { weights: { trend: 1, momentum: 1, macd: 1, bollinger: 1 } },
    status: "PROPOSED",
    decided_at: null,
    decision_comment: null,
    created_at: "2026-07-01T00:00:00+00:00",
  };

  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";

      if (path === "/api/v1/strategy-versions/1" && method === "GET") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(version) });
      }
      if (path === "/api/v1/strategy-versions/1/compare" && method === "POST") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              candidate_backtest: makeBacktest({ id: 1 }),
              active_backtest: makeBacktest({ id: 2, results_summary: { ...makeBacktest().results_summary, total_return_pct: "6.00" } }),
              delta: {
                total_return_pct: "4.00",
                max_drawdown_pct: "-1.00",
                win_rate_pct: "2.00",
                avg_win_pct: "0.50",
                avg_loss_pct: "-0.20",
                num_trades: 3,
              },
            }),
        });
      }
      if (path === "/api/v1/strategy-versions/1/approve" && method === "POST") {
        if (approveStatus !== 200) {
          return Promise.resolve({
            ok: false,
            status: approveStatus,
            json: () => Promise.resolve({ detail: "This version is no longer PROPOSED." }),
          });
        }
        version = { ...version, status: "ACTIVE", decided_at: "2026-08-01T00:00:00+00:00" };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(version) });
      }
      if (path === "/api/v1/strategy-versions/1/reject" && method === "POST") {
        version = { ...version, status: "REJECTED", decided_at: "2026-08-01T00:00:00+00:00" };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(version) });
      }
      return Promise.reject(new Error(`No mock handler for ${method} ${path}`));
    }),
  );
}

describe("StrategyVersionDetailPage — propose→compare→approve/reject state machine", () => {
  beforeEach(() => {
    mockFetch();
  });

  it("shows the Review card with Compare/Approve/Reject only while PROPOSED", async () => {
    renderWithQueryClient(<StrategyVersionDetailPage />);
    await waitFor(() => expect(screen.getByText("Candidate v2")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Compare against active" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
  });

  it("renders the comparison delta after Compare against active", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<StrategyVersionDetailPage />);
    await waitFor(() => expect(screen.getByText("Candidate v2")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Compare against active" }));

    // The "+" prefix and value render as separate text nodes (see CompareView.tsx),
    // so match on the container's combined textContent rather than exact text.
    await waitFor(() =>
      expect(
        screen.getByText((_, element) => element?.textContent === "+4.00%"),
      ).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("equity-curve-chart-stub")).toHaveLength(2);
  });

  it("requires a second click through ConfirmButton before rejecting, then flips status", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<StrategyVersionDetailPage />);
    await waitFor(() => expect(screen.getByText("Candidate v2")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
    expect(screen.getByText("PROPOSED")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Confirm rejection" }));

    await waitFor(() => expect(screen.getByText("REJECTED")).toBeInTheDocument());
    // Once no longer PROPOSED, the Review card (Compare/Approve/Reject) disappears.
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("surfaces an approve error via ErrorBanner and leaves status unchanged", async () => {
    mockFetch({ approveStatus: 400 });
    const user = userEvent.setup();
    renderWithQueryClient(<StrategyVersionDetailPage />);
    await waitFor(() => expect(screen.getByText("Candidate v2")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "The request couldn't be completed as sent.",
      ),
    );
    expect(screen.getByText("PROPOSED")).toBeInTheDocument();
  });
});
