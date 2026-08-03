import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe("Home", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({ status: "ok", time_utc: "2026-08-03T00:00:00+00:00" }),
      }),
    );
  });

  it("renders the TradingOS heading and reports healthy API status", async () => {
    renderWithQueryClient(<Home />);

    expect(screen.getByText("TradingOS")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("api-status")).toHaveTextContent("API status: ok");
    });
  });
});
