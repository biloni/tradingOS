"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Input } from "@/components/ui/Input";
import { useLogin, useSession } from "@/lib/hooks/useSession";

/**
 * Revision Prompt 16, ADR-066: the single-user password gate. There is no
 * "create account" flow by design (docs/RUNBOOK.md documents the CLI-only
 * `python -m tradingos_api.scripts.set_password` bootstrap) — this page
 * only ever authenticates the one already-provisioned user.
 */
export default function LoginPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const loginMutation = useLogin();
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (session?.authenticated) {
      router.replace("/");
    }
  }, [session, router]);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    loginMutation.mutate(password, {
      onSuccess: () => router.replace("/"),
    });
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold text-black dark:text-zinc-50">
          TradingOS
        </h1>
        <p className="mb-6 text-sm text-zinc-500 dark:text-zinc-400">
          Sign in to continue.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="password"
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              data-testid="login-password"
            />
          </div>
          <ErrorBanner error={loginMutation.error} />
          <Button
            type="submit"
            className="w-full"
            disabled={loginMutation.isPending || password.length === 0}
            data-testid="login-submit"
          >
            {loginMutation.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
