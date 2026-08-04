"use client";

import { useState } from "react";
import { Button } from "./Button";

/**
 * The inline two-step human-confirmation gate (principles 11/16) used
 * everywhere an action is irreversible: order confirm, strategy approve,
 * strategy reject. Deliberately not a modal — a full accessible dialog
 * (focus trap, ESC handling, backdrop) is real a11y work this personal,
 * single-user app doesn't need; a second explicit click satisfies the
 * same "confirm immediately before the action" requirement (ADR-029).
 */
export function ConfirmButton({
  label,
  confirmLabel = "Confirm",
  onConfirm,
  disabled,
  variant = "primary",
}: {
  label: string;
  confirmLabel?: string;
  onConfirm: () => void;
  disabled?: boolean;
  variant?: "primary" | "danger";
}) {
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <Button variant={variant} disabled={disabled} onClick={() => setConfirming(true)}>
        {label}
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-zinc-600 dark:text-zinc-400">Are you sure?</span>
      <Button
        variant={variant}
        disabled={disabled}
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </Button>
      <Button variant="ghost" onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}
