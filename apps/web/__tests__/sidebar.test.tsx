import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

import { Sidebar } from "@/components/layout/Sidebar";

/**
 * R2 required routes + backward compatibility: every new placeholder
 * route must have a nav entry, and every pre-existing route (untouched
 * by this revision) must remain linked too.
 */
describe("Sidebar navigation", () => {
  it("links to every new R2 route", () => {
    render(<Sidebar />);
    for (const [label, href] of [
      ["Morning Dashboard", "/"],
      ["Investment", "/investment"],
      ["Tactical Trades", "/tactical"],
      ["Earnings Center", "/earnings"],
      ["Approval Queue", "/approvals"],
      ["Orders and Fills", "/orders"],
      ["Watchlists", "/watchlists"],
      ["Agent Review", "/agent-review"],
      ["Journal", "/journal"],
      ["Alerts", "/alerts"],
      ["Performance", "/performance"],
      ["Settings", "/settings"],
    ] as const) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("href", href);
    }
  });

  it("still links to every pre-existing route, unchanged", () => {
    render(<Sidebar />);
    for (const [label, href] of [
      ["Portfolio", "/portfolio"],
      ["Symbols", "/symbols"],
      ["Ask", "/ask"],
      ["Backtests", "/backtests"],
      ["Strategy", "/strategy-versions"],
    ] as const) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("href", href);
    }
  });

  it("keeps the old Dashboard content reachable at /legacy-dashboard rather than deleting it", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Legacy Dashboard" })).toHaveAttribute(
      "href",
      "/legacy-dashboard",
    );
  });

  it("marks the current route with aria-current for accessibility", () => {
    render(<Sidebar />);
    expect(screen.getByRole("link", { name: "Morning Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
