"use client";

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
  { href: "/settings", label: "Settings" },
  { href: "/legacy-dashboard", label: "Legacy Dashboard" },
];

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <li>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
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

export function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav className="w-56 shrink-0 overflow-y-auto border-r border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-6 px-2 text-lg font-semibold tracking-tight text-black dark:text-zinc-50">
        TradingOS
      </div>
      <ul className="space-y-1">
        {PRIMARY_LINKS.map((link) => (
          <NavLink key={link.href} {...link} active={isActive(link.href)} />
        ))}
      </ul>
      <hr className="my-4 border-zinc-200 dark:border-zinc-800" />
      <ul className="space-y-1">
        {SECONDARY_LINKS.map((link) => (
          <NavLink key={link.href} {...link} active={isActive(link.href)} />
        ))}
      </ul>
    </nav>
  );
}
