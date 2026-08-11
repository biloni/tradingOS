"use client";

import { useRouter } from "next/navigation";
import { useLogout, useSession } from "@/lib/hooks/useSession";

export function LogoutButton() {
  const router = useRouter();
  const { data } = useSession();
  const logoutMutation = useLogout();

  if (!data?.authenticated) return null;

  return (
    <button
      type="button"
      onClick={() =>
        logoutMutation.mutate(undefined, { onSuccess: () => router.replace("/login") })
      }
      disabled={logoutMutation.isPending}
      data-testid="logout-button"
      className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
    >
      {logoutMutation.isPending ? "Signing out…" : "Sign out"}
    </button>
  );
}
