import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AskPage from "@/app/ask/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockAskResponse(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: status === 200,
        status,
        json: () => Promise.resolve(body),
      }),
    ),
  );
}

async function askQuestion(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(
    screen.getByPlaceholderText("Ask a question about the tracked symbols…"),
    text,
  );
  await user.click(screen.getByRole("button", { name: "Send" }));
}

describe("AskPage", () => {
  it("renders an answer with no recommendations block when the list is empty", async () => {
    mockAskResponse({
      answer: "There are no symbols matching that filter right now.",
      recommendations: [],
      llm_call_log_ids: [1],
      iterations: 1,
    });
    const user = userEvent.setup();
    renderWithQueryClient(<AskPage />);

    await askQuestion(user, "Anything below band in G&A?");

    await waitFor(() =>
      expect(
        screen.getByText("There are no symbols matching that filter right now."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText(/score \d/)).not.toBeInTheDocument();
  });

  it("renders recommendation chips (ticker, score, confidence pill) when populated", async () => {
    mockAskResponse({
      answer: "AAPL and MSFT look aligned for a swing entry.",
      recommendations: [
        {
          recommendation_id: 1,
          symbol_ticker: "AAPL",
          score: "0.72",
          confidence: "HIGH",
          signal_breakdown: { trend: 1, momentum: 1 },
        },
      ],
      llm_call_log_ids: [1],
      iterations: 2,
    });
    const user = userEvent.setup();
    renderWithQueryClient(<AskPage />);

    await askQuestion(user, "What does AAPL's current setup look like?");

    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());
    expect(screen.getByText("score 0.72")).toBeInTheDocument();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("shows the 429 rate-limit copy via ErrorBanner", async () => {
    mockAskResponse({ detail: "Rate limited" }, 429);
    const user = userEvent.setup();
    renderWithQueryClient(<AskPage />);

    await askQuestion(user, "one more question");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "You're asking questions faster than the configured limit",
      ),
    );
  });

  it("shows the 503 no-API-key copy via ErrorBanner", async () => {
    mockAskResponse({ detail: "unavailable" }, 503);
    const user = userEvent.setup();
    renderWithQueryClient(<AskPage />);

    await askQuestion(user, "one more question");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Natural-language query isn't available right now",
      ),
    );
  });

  it("shows the 422 validation copy via ErrorBanner", async () => {
    mockAskResponse({ detail: "too long" }, 422);
    const user = userEvent.setup();
    renderWithQueryClient(<AskPage />);

    await askQuestion(user, "one more question");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Questions must be between 1 and 2000 characters.",
      ),
    );
  });
});
