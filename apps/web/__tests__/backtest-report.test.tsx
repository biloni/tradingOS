import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BacktestReport } from "@/components/backtests/BacktestReport";
import type { BacktestRun } from "@/lib/api/backtests";

// jsdom has no real <canvas> 2D context, so lightweight-charts can't mount —
// these tests cover BacktestReport's data-shape (metrics, trade-log rows,
// empty states) rather than actual chart rendering, per the component-test
// plan's priority-5 note for chart-adjacent components.
vi.mock("@/components/charts/EquityCurveChart", () => ({
  EquityCurveChart: () => <div data-testid="equity-curve-chart-stub" />,
}));

function makeRun(overrides: Partial<BacktestRun["results_summary"]> = {}): BacktestRun {
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
      ending_equity: "11502.81",
      total_return_pct: "15.03",
      max_drawdown_pct: "-8.20",
      win_rate_pct: "52.00",
      num_trades: 847,
      avg_win_pct: "2.10",
      avg_loss_pct: "-1.40",
      benchmark_return_pct: "44.39",
      equity_curve: [{ as_of: "2026-01-02", equity: "10000.00" }],
      trades: [
        {
          ticker: "AAPL",
          entry_date: "2026-01-05",
          entry_price: "300.00",
          exit_date: "2026-01-20",
          exit_price: "310.00",
          quantity: 10,
          pnl_usd: "100.00",
          pnl_pct: "3.33",
          exit_reason: "SIGNAL_EXIT",
        },
      ],
      ...overrides,
    },
    created_at: "2026-07-01T00:00:00+00:00",
  };
}

describe("BacktestReport", () => {
  it("renders the summary metrics grid with correctly formatted values", () => {
    render(<BacktestReport run={makeRun()} title="Candidate" />);

    expect(screen.getByText("Candidate")).toBeInTheDocument();
    expect(screen.getByText("$11,502.81")).toBeInTheDocument();
    expect(screen.getByText("15.03%")).toBeInTheDocument();
    expect(screen.getByText("847")).toBeInTheDocument();
    expect(screen.getByText("44.39%")).toBeInTheDocument();
  });

  it("renders one trade-log row per trade with a StatusPill for exit_reason", () => {
    render(<BacktestReport run={makeRun()} />);

    expect(screen.getByText("Trade log (1)")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("SIGNAL EXIT")).toBeInTheDocument();
  });

  it("shows empty-state copy instead of a table when there are no trades", () => {
    render(<BacktestReport run={makeRun({ trades: [] })} />);

    expect(screen.getByText("No trades in this run.")).toBeInTheDocument();
  });

  it("shows empty-state copy instead of a chart when the equity curve is empty", () => {
    render(<BacktestReport run={makeRun({ equity_curve: [] })} />);

    expect(screen.getByText("No equity curve data.")).toBeInTheDocument();
    expect(screen.queryByTestId("equity-curve-chart-stub")).not.toBeInTheDocument();
  });

  it("shows an em dash for a null benchmark_return_pct instead of crashing", () => {
    render(<BacktestReport run={makeRun({ benchmark_return_pct: null })} />);

    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
