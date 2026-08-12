import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EarningsResearchPage from "@/app/earnings-research/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockResearchResponse(body: unknown, status = 200) {
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

async function submitCompany(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(
    screen.getByPlaceholderText("Company name or ticker, e.g. Marvell Technology or MRVL"),
    text,
  );
  await user.click(screen.getByRole("button", { name: "Research" }));
}

describe("EarningsResearchPage", () => {
  it("renders the answer and source links on success", async () => {
    mockResearchResponse({
      answer: "MRVL reports 2026-12-01. Consensus EPS is $1.35.",
      sources: [{ url: "https://a.example/1", title: "Estimates" }],
      model_call_record_ids: ["11111111-1111-1111-1111-111111111111"],
      iterations: 1,
    });
    const user = userEvent.setup();
    renderWithQueryClient(<EarningsResearchPage />);

    await submitCompany(user, "Marvell Technology");

    await waitFor(() =>
      expect(screen.getByText(/Consensus EPS is \$1\.35/)).toBeInTheDocument(),
    );
    const link = screen.getByRole("link", { name: "Estimates" });
    expect(link).toHaveAttribute("href", "https://a.example/1");
    expect(
      screen.getByText("Educational research only — not investment advice. A human must decide."),
    ).toBeInTheDocument();
  });

  it("renders without a sources section when none were returned", async () => {
    mockResearchResponse({
      answer: "Could not verify this company via search.",
      sources: [],
      model_call_record_ids: ["11111111-1111-1111-1111-111111111111"],
      iterations: 1,
    });
    const user = userEvent.setup();
    renderWithQueryClient(<EarningsResearchPage />);

    await submitCompany(user, "Not A Real Company");

    await waitFor(() =>
      expect(screen.getByText("Could not verify this company via search.")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("shows the 429 rate-limit copy via ErrorBanner", async () => {
    mockResearchResponse({ detail: "Rate limited" }, 429);
    const user = userEvent.setup();
    renderWithQueryClient(<EarningsResearchPage />);

    await submitCompany(user, "Marvell Technology");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "You're requesting research faster than the configured limit",
      ),
    );
  });

  it("shows the 503 no-API-key copy via ErrorBanner", async () => {
    mockResearchResponse({ detail: "unavailable" }, 503);
    const user = userEvent.setup();
    renderWithQueryClient(<EarningsResearchPage />);

    await submitCompany(user, "Marvell Technology");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Earnings research isn't available right now",
      ),
    );
  });
});
