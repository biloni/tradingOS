import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/Sidebar";
import { EnvironmentBanner } from "@/components/layout/EnvironmentBanner";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { AuthGate } from "@/components/layout/AuthGate";
import { LogoutButton } from "@/components/layout/LogoutButton";

// Applies the persisted (or system-default) theme class before first
// paint — `beforeInteractive` runs ahead of hydration, so there is no
// flash of the wrong theme. Wrapped in try/catch: `localStorage` can
// throw in locked-down browser contexts, and a theme flicker is a far
// smaller problem than a blocked page render.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem("tradingos-theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TradingOS",
  description: "Decision-support for swing trading — research and paper-trading mode.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
      </head>
      <body className="min-h-full flex flex-col">
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <Providers>
          <div className="flex items-stretch">
            <div className="flex-1">
              <EnvironmentBanner />
            </div>
            <div className="flex shrink-0 items-center gap-2 border-b border-zinc-200 bg-white px-3 dark:border-zinc-800 dark:bg-zinc-950">
              <ThemeToggle />
              <LogoutButton />
            </div>
          </div>
          <div className="flex min-h-full flex-1">
            <Sidebar />
            <main
              id="main-content"
              tabIndex={-1}
              className="min-w-0 flex-1 bg-zinc-50 dark:bg-black"
            >
              <AuthGate>{children}</AuthGate>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
