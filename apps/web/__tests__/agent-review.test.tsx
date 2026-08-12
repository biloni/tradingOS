import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AgentReviewPage from "@/app/agent-review/page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

function renderWithQueryClient() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AgentReviewPage />
    </QueryClientProvider>,
  );
}

function sessionFixture() {
  return {
    session_id: "session-1",
    lane: "INVESTMENT",
    status: "COMPLETED",
    role_runs: [
      {
        role: "BULL",
        display_name: "Bull",
        status: "SUCCEEDED",
        error_detail: null,
        output: { categorical_stance: "BULLISH", rationale: "Strong revenue growth." },
        model: "claude-opus-5",
        input_tokens: 500,
        output_tokens: 200,
        latency_ms: 1200,
        cost_usd: "0.0500",
      },
    ],
    total_cost_usd: "0.0500",
    recommendation_id: "rec-1",
    lane_action: "INVEST_BUY",
    veto_override_applied: false,
  };
}

function mockFetch(session: ReturnType<typeof sessionFixture>) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/committee/sessions/")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(session) });
      }
      return Promise.reject(new Error(`No mock response for ${url}`));
    }),
  );
}

describe("Agent Review page", () => {
  it("prompts for a session ID before anything is loaded", () => {
    mockFetch(sessionFixture());
    renderWithQueryClient();
    expect(screen.getByRole("heading", { level: 1, name: "Agent Review" })).toBeInTheDocument();
    expect(screen.getByText(/Enter a committee session ID above/)).toBeInTheDocument();
  });

  it("loads and displays a real committee session by ID", async () => {
    mockFetch(sessionFixture());
    renderWithQueryClient();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Session ID"), "session-1");
    await user.click(screen.getByRole("button", { name: "Load session" }));

    await waitFor(() => {
      expect(screen.getByText("Bull")).toBeInTheDocument();
    });
    expect(screen.getByText("SUCCEEDED")).toBeInTheDocument();
    expect(screen.getByText("BULLISH")).toBeInTheDocument();
    expect(screen.getByText(/Lane action: INVEST_BUY/)).toBeInTheDocument();
  });
});
