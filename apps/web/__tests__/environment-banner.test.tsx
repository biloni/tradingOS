import { readFileSync } from "node:fs";
import path from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EnvironmentBanner } from "@/components/layout/EnvironmentBanner";

function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockOperatingModeResponse(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve(body) }),
  );
}

describe("EnvironmentBanner", () => {
  it(
    "cannot be hidden by a query parameter: the component source never reads " +
      "useSearchParams, window.location, or any URL-derived value",
    () => {
      const fullSource = readFileSync(
        path.resolve(import.meta.dirname, "../components/layout/EnvironmentBanner.tsx"),
        "utf-8",
      );
      // Strip the file's own /** ... */ doc comment (which *discusses*
      // these APIs in prose) before checking for actual usage — this
      // test must catch a real `useSearchParams()` call being added
      // later, not trip on the explanation of why there isn't one.
      const codeOnly = fullSource.replace(/\/\*[\s\S]*?\*\//g, "");
      expect(codeOnly).not.toMatch(/useSearchParams\s*\(/);
      expect(codeOnly).not.toMatch(/window\.location/);
      expect(codeOnly).not.toMatch(/next\/navigation/);
      // And structurally: the component accepts no props at all, so there
      // is no visibility flag a caller (or a URL-driven caller) could pass.
      expect(codeOnly).toMatch(/export function EnvironmentBanner\(\)/);
    },
  );

  it("shows a loading state, then RESEARCH for RESEARCH_ONLY mode", async () => {
    mockOperatingModeResponse({
      mode: "RESEARCH_ONLY",
      environment_label: "RESEARCH",
      can_submit_orders: false,
    });
    renderWithQueryClient(<EnvironmentBanner />);
    expect(screen.getByTestId("environment-banner")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("environment-banner")).toHaveTextContent("RESEARCH");
    });
  });

  it("shows PAPER for either paper mode", async () => {
    mockOperatingModeResponse({
      mode: "PAPER_AUTO_POLICY",
      environment_label: "PAPER",
      can_submit_orders: true,
    });
    renderWithQueryClient(<EnvironmentBanner />);
    await waitFor(() => {
      expect(screen.getByTestId("environment-banner")).toHaveTextContent("PAPER");
    });
  });

  it("shows LIVE for the live-confirm mode", async () => {
    mockOperatingModeResponse({
      mode: "LIVE_CONFIRM_EACH_ORDER",
      environment_label: "LIVE",
      can_submit_orders: true,
    });
    renderWithQueryClient(<EnvironmentBanner />);
    await waitFor(() => {
      expect(screen.getByTestId("environment-banner")).toHaveTextContent("LIVE");
    });
  });

  it("never disappears on an API error — degrades to an explicit unknown-environment alert", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    renderWithQueryClient(<EnvironmentBanner />);
    await waitFor(() => {
      const banner = screen.getByTestId("environment-banner");
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveTextContent("ENVIRONMENT UNKNOWN");
      expect(banner).toHaveAttribute("role", "alert");
    });
  });
});
