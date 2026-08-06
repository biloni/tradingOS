import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InvestmentPage from "@/app/investment/page";
import TacticalPage from "@/app/tactical/page";
import EarningsCenterPage from "@/app/earnings/page";
import ApprovalQueuePage from "@/app/approvals/page";
import OrdersAndFillsPage from "@/app/orders/page";
import JournalPage from "@/app/journal/page";
import PerformancePage from "@/app/performance/page";
import WatchlistsPage from "@/app/watchlists/page";
import AlertsPage from "@/app/alerts/page";
import AgentReviewPage from "@/app/agent-review/page";
import SettingsPage from "@/app/settings/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

// Every new Revision Prompt R2 route must render its own synthetic
// placeholder content and a scaffold notice, without crashing and
// without needing any live data beyond the operating-mode endpoint.
const ROUTES: Array<{ label: string; heading: string; Component: () => React.JSX.Element }> = [
  { label: "/investment", heading: "Investment", Component: InvestmentPage },
  { label: "/tactical", heading: "Tactical Trades", Component: TacticalPage },
  { label: "/earnings", heading: "Earnings Center", Component: EarningsCenterPage },
  { label: "/approvals", heading: "Approval Queue", Component: ApprovalQueuePage },
  { label: "/journal", heading: "Journal", Component: JournalPage },
  { label: "/performance", heading: "Performance", Component: PerformancePage },
  { label: "/watchlists", heading: "Watchlists", Component: WatchlistsPage },
  { label: "/alerts", heading: "Alerts", Component: AlertsPage },
  { label: "/agent-review", heading: "Agent Review", Component: AgentReviewPage },
];

describe.each(ROUTES)("scaffold route $label", ({ heading, Component }) => {
  it(`renders the "${heading}" heading and a scaffold notice`, () => {
    renderWithQueryClient(<Component />);
    expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.getByText(/Scaffold page \(Revision Prompt R2\)/)).toBeInTheDocument();
  });
});

describe("scaffold routes that read the operating-mode API", () => {
  beforeEach(() => {
    mockOperatingMode();
  });

  it("Orders and Fills renders and shows not-implemented kill-switch/cancel-all placeholders", async () => {
    renderWithQueryClient(<OrdersAndFillsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Orders and Fills" })).toBeInTheDocument();
    expect(screen.getByTestId("kill-switch-placeholder")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("cancel-all-placeholder")).toHaveAttribute("aria-disabled", "true");
    await waitFor(() => {
      expect(screen.getByTestId("operating-mode-status")).toHaveTextContent("Research only");
    });
  });

  it("Settings renders the read-only operating-mode status from the API", async () => {
    renderWithQueryClient(<SettingsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("operating-mode-status")).toHaveTextContent("Research only");
    });
  });
});
