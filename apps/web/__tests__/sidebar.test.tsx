import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      ["Earnings Research", "/earnings-research"],
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

/**
 * Revision Prompt 15 — mobile layout must not let the sidebar eat the
 * whole viewport. Below `md`, the nav is an off-canvas drawer closed by
 * default; these tests don't assert on the CSS breakpoint itself
 * (jsdom has no real viewport), only on the toggle's actual open/close
 * behavior and its accessible state.
 */
describe("Sidebar mobile off-canvas toggle", () => {
  it("starts closed and opens on toggle, with aria-expanded reflecting state", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    const toggle = screen.getByRole("button", { name: "Open navigation menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("closes when a nav link is activated, so navigating doesn't leave the drawer open", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    await user.click(screen.getByRole("button", { name: "Open navigation menu" }));
    expect(screen.getByRole("button", { name: "Open navigation menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    await user.click(screen.getByRole("link", { name: "Portfolio" }));
    expect(screen.getByRole("button", { name: "Open navigation menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("closes via the explicit close button", async () => {
    const user = userEvent.setup();
    render(<Sidebar />);

    await user.click(screen.getByRole("button", { name: "Open navigation menu" }));
    await user.click(screen.getByRole("button", { name: "Close navigation menu" }));
    expect(screen.getByRole("button", { name: "Open navigation menu" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });
});
