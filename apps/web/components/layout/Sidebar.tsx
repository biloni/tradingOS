"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/symbols", label: "Symbols" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/ask", label: "Ask" },
  { href: "/backtests", label: "Backtests" },
  { href: "/strategy-versions", label: "Strategy" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="w-56 shrink-0 border-r border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-6 px-2 text-lg font-semibold tracking-tight text-black dark:text-zinc-50">
        TradingOS
      </div>
      <ul className="space-y-1">
        {LINKS.map((link) => {
          const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <li key={link.href}>
              <Link
                href={link.href}
                className={`block rounded-md px-3 py-2 text-sm font-medium ${
                  active
                    ? "bg-black text-white dark:bg-zinc-50 dark:text-black"
                    : "text-zinc-700 hover:bg-zinc-200 dark:text-zinc-300 dark:hover:bg-zinc-800"
                }`}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
