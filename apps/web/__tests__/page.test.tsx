import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MorningDashboardPage from "@/app/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockOperatingMode() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/api/v1/settings/operating-mode")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              mode: "RESEARCH_ONLY",
              environment_label: "RESEARCH",
              can_submit_orders: false,
            }),
        });
      }
      return Promise.reject(new Error(`No mock response for ${url}`));
    }),
  );
}

describe("MorningDashboardPage", () => {
  beforeEach(() => {
    mockOperatingMode();
  });

  it("renders the Morning Decision Dashboard heading", () => {
    renderWithQueryClient(<MorningDashboardPage />);
    expect(screen.getByText("Morning Decision Dashboard")).toBeInTheDocument();
  });

  it("renders all seven fixed sections in order", () => {
    renderWithQueryClient(<MorningDashboardPage />);
    const expected = [
      "Act Now",
      "Approval Required",
      "Hold / Manage",
      "Investment Watch",
      "Tactical Watch",
      "Avoid",
      "Data Problems",
    ];
    const headings = screen.getAllByRole("heading", { level: 2 }).map((el) => el.textContent);
    for (const label of expected) {
      expect(headings.some((h) => h?.startsWith(label))).toBe(true);
    }
  });

  it("shows the scaffold notice", () => {
    renderWithQueryClient(<MorningDashboardPage />);
    expect(screen.getByText(/Scaffold page \(Revision Prompt R2\)/)).toBeInTheDocument();
  });

  it("shows the incomplete-plan banner as an alert", () => {
    renderWithQueryClient(<MorningDashboardPage />);
    expect(screen.getByText("This plan is INCOMPLETE").closest('[role="alert"]')).not.toBeNull();
  });

  it("renders the operating-mode status from the API", async () => {
    renderWithQueryClient(<MorningDashboardPage />);
    await waitFor(() => {
      expect(screen.getByTestId("operating-mode-status")).toHaveTextContent("Research only");
    });
  });
});
