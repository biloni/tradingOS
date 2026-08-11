import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import OpsPage from "@/app/ops/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const METRICS = {
  uptime_seconds: 125,
  total_requests: 42,
  status_class_counts: { "2xx": 40, "4xx": 2 },
  latency: { avg_ms: 12.5, p50_ms: 10, p95_ms: 30, sample_size: 42 },
};

const JOB_RUNS = [
  {
    id: "run-1",
    plan_date: "2026-08-11",
    status: "COMPLETED",
    triggered_by: "worker-demo",
    started_at: "2026-08-11T06:10:00Z",
    completed_at: "2026-08-11T06:10:42Z",
    duration_seconds: 42,
    error_detail: null,
  },
  {
    id: "run-2",
    plan_date: "2026-08-10",
    status: "FAILED",
    triggered_by: "worker-demo",
    started_at: "2026-08-10T05:45:00Z",
    completed_at: "2026-08-10T05:45:05Z",
    duration_seconds: 5,
    error_detail: "provider timeout",
  },
];

const COST_BUDGET = {
  daily_spend_usd: "1.50",
  daily_budget_usd: "5.00",
  budget_remaining_usd: "3.50",
  kill_switch_active: false,
  as_of: "2026-08-11T12:00:00Z",
};

function mockFetch({
  jobRuns = JOB_RUNS,
  costBudget = COST_BUDGET,
}: { jobRuns?: typeof JOB_RUNS; costBudget?: typeof COST_BUDGET } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      if (path === "/api/v1/ops/metrics") {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(METRICS) });
      }
      if (path.startsWith("/api/v1/ops/job-runs")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(jobRuns) });
      }
      if (path === "/api/v1/ops/cost-budget") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(costBudget),
        });
      }
      return Promise.reject(new Error(`No mock handler for GET ${path}`));
    }),
  );
}

describe("OpsPage", () => {
  beforeEach(() => {
    mockFetch();
  });

  it("renders process metrics", async () => {
    renderWithQueryClient(<OpsPage />);
    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("2m 5s")).toBeInTheDocument();
    expect(screen.getByText("13ms")).toBeInTheDocument();
    expect(screen.getByText("30ms")).toBeInTheDocument();
  });

  it("renders job runs most-recent-first with status pills", async () => {
    renderWithQueryClient(<OpsPage />);
    await waitFor(() => expect(screen.getByText("2026-08-11")).toBeInTheDocument());
    expect(screen.getByText("COMPLETED")).toBeInTheDocument();
    expect(screen.getByText("FAILED")).toBeInTheDocument();
    expect(screen.getByText("provider timeout")).toBeInTheDocument();
  });

  it("shows an empty state when there are no job runs", async () => {
    mockFetch({ jobRuns: [] });
    renderWithQueryClient(<OpsPage />);
    await waitFor(() =>
      expect(screen.getByText("No job runs recorded yet")).toBeInTheDocument(),
    );
  });

  it("renders the cost budget panel", async () => {
    renderWithQueryClient(<OpsPage />);
    await waitFor(() => expect(screen.getByText("$1.50")).toBeInTheDocument());
    expect(screen.getByText("$5.00")).toBeInTheDocument();
    expect(screen.getByText("$3.50")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("warns when the cost budget has tripped the kill switch", async () => {
    mockFetch({ costBudget: { ...COST_BUDGET, kill_switch_active: true } });
    renderWithQueryClient(<OpsPage />);
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Kill switch is active"),
    );
  });
});
