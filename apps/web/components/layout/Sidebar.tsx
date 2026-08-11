"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

// Ordering matches docs/UX_MAP.md's R1/R2 navigation: the new
// morning-plan/committee/order-lifecycle loop first, existing Phase 1-7
// pages after a divider, kept fully backward compatible (same hrefs).
const PRIMARY_LINKS = [
  { href: "/", label: "Morning Dashboard" },
  { href: "/investment", label: "Investment" },
  { href: "/tactical", label: "Tactical Trades" },
  { href: "/earnings", label: "Earnings Center" },
  { href: "/approvals", label: "Approval Queue" },
  { href: "/orders", label: "Orders and Fills" },
  { href: "/watchlists", label: "Watchlists" },
  { href: "/agent-review", label: "Agent Review" },
  { href: "/journal", label: "Journal" },
  { href: "/alerts", label: "Alerts" },
  { href: "/performance", label: "Performance" },
];

const SECONDARY_LINKS = [
  { href: "/portfolio", label: "Portfolio" },
  { href: "/symbols", label: "Symbols" },
  { href: "/ask", label: "Ask" },
  { href: "/backtests", label: "Backtests" },
  { href: "/strategy-versions", label: "Strategy" },
  { href: "/ops", label: "Operations" },
  { href: "/settings", label: "Settings" },
  { href: "/legacy-dashboard", label: "Legacy Dashboard" },
];

function NavLink({
  href,
  label,
  active,
  onNavigate,
}: {
  href: string;
  label: string;
  active: boolean;
  onNavigate: () => void;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
        onClick={onNavigate}
        className={`block rounded-md px-3 py-2 text-sm font-medium ${
          active
            ? "bg-black text-white dark:bg-zinc-50 dark:text-black"
            : "text-zinc-700 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-800"
        }`}
      >
        {label}
      </Link>
    </li>
  );
}

/**
 * Revision Prompt 15's "mobile layout must support review and approval"
 * requirement starts with the nav not eating the whole viewport: below
 * the `md` breakpoint the sidebar is an off-canvas drawer (closed by
 * default, toggled by a hamburger button), not a permanent 224px-wide
 * column — the same collapse pattern this app's own `PageState`/badge
 * components already use text+icon for (never relying on screen space
 * alone to communicate state).
 */
export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        aria-expanded={open}
        data-testid="mobile-nav-toggle"
        className="fixed left-3 top-14 z-30 rounded-md border border-zinc-300 bg-white p-2 text-zinc-700 shadow-sm md:hidden dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
      >
        <span aria-hidden="true">&#9776;</span>
        <span className="sr-only">Open navigation menu</span>
      </button>

      {open && (
        <div
          aria-hidden="true"
          onClick={close}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
        />
      )}

      <nav
        aria-label="Primary"
        className={`fixed inset-y-0 left-0 z-40 w-56 shrink-0 overflow-y-auto border-r border-zinc-200 bg-zinc-50 p-4 transition-transform duration-150 md:sticky md:top-0 md:h-screen md:translate-x-0 dark:border-zinc-800 dark:bg-zinc-950 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-center justify-between px-2">
          <span className="text-lg font-semibold tracking-tight text-black dark:text-zinc-50">
            TradingOS
          </span>
          <button
            type="button"
            onClick={close}
            aria-label="Close navigation menu"
            className="rounded-md p-1 text-zinc-500 md:hidden dark:text-zinc-400"
          >
            &#10005;
          </button>
        </div>
        <ul className="space-y-1">
          {PRIMARY_LINKS.map((link) => (
            <NavLink key={link.href} {...link} active={isActive(link.href)} onNavigate={close} />
          ))}
        </ul>
        <hr className="my-4 border-zinc-200 dark:border-zinc-800" />
        <ul className="space-y-1">
          {SECONDARY_LINKS.map((link) => (
            <NavLink key={link.href} {...link} active={isActive(link.href)} onNavigate={close} />
          ))}
        </ul>
      </nav>
    </>
  );
}
