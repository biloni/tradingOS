"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "@/lib/hooks/useSession";

const PUBLIC_PATHS = new Set(["/login"]);

/**
 * Revision Prompt 16, ADR-066: client-side route guard. Every business
 * route in `main.py` is behind `require_session` now, so an
 * unauthenticated visit to any page beyond `/login` would otherwise just
 * render a wall of 401 errors — this redirects to `/login` before that
 * happens. Deliberately a client component polling `GET /auth/session`
 * (already cheap and cached by react-query) rather than Next.js
 * middleware: middleware would need its own fetch to the API to validate
 * the opaque session token, which duplicates this exact round trip at the
 * edge for no real benefit in a single-user local app.
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.has(pathname);
  const { data, isLoading, isError } = useSession();

  useEffect(() => {
    if (isPublic || isLoading) return;
    if (isError || !data?.authenticated) {
      router.replace("/login");
    }
  }, [isPublic, isLoading, isError, data, router]);

  if (isPublic) {
    return <>{children}</>;
  }

  if (isLoading || isError || !data?.authenticated) {
    return (
      <div
        role="status"
        className="flex min-h-[50vh] items-center justify-center text-sm text-zinc-500 dark:text-zinc-400"
      >
        Checking session&hellip;
      </div>
    );
  }

  return <>{children}</>;
}
