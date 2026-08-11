"use client";

import { useState } from "react";
import { Button } from "./Button";
import { ErrorBanner } from "./ErrorBanner";
import { Input } from "./Input";
import { useSession, useStepUp } from "@/lib/hooks/useSession";

/**
 * Revision Prompt 16 — gates a sensitive action (order approve/submit;
 * kill-switch deactivate and cancel-all aren't wired to any UI yet, see
 * app/orders/page.tsx's scaffold notice) behind a fresh password
 * re-entry. The backend enforces this independently
 * (`core/dependencies.py::require_step_up`, 403 without it) — this
 * component exists so the user gets a usable prompt instead of a
 * silent failure, never as the actual security boundary.
 */
export function StepUpGate({
  children,
  reason,
}: {
  children: React.ReactNode;
  reason: string;
}) {
  const { data: session } = useSession();
  const stepUp = useStepUp();
  const [password, setPassword] = useState("");

  if (session?.stepped_up) {
    return <>{children}</>;
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    stepUp.mutate(password, { onSuccess: () => setPassword("") });
  }

  return (
    <div
      role="group"
      aria-label="Step-up confirmation required"
      className="rounded-md border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950"
    >
      <p className="mb-2 text-sm font-medium text-amber-900 dark:text-amber-200">
        Re-enter your password to continue — {reason}.
      </p>
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <div className="flex-1">
          <Input
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            data-testid="step-up-password"
          />
        </div>
        <Button type="submit" disabled={stepUp.isPending || password.length === 0}>
          {stepUp.isPending ? "Confirming…" : "Confirm"}
        </Button>
      </form>
      <ErrorBanner error={stepUp.error} />
    </div>
  );
}
