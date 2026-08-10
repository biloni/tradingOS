"use client";

import { useState } from "react";
import type { MorningPlanItem } from "@/lib/api/morningPlan";
import { Card } from "@/components/ui/Card";
import { PageState } from "@/components/ui/PageState";
import { DashboardCard } from "@/components/dashboard/DashboardCard";

/**
 * One section of the dashboard's fixed hierarchy (Revision Prompt 15).
 * `cap` implements "Act Now" own "no more than 3 actionable entries at a
 * glance" rule (docs/MORNING_PLAN_SPEC.md) — additional qualifying items
 * stay in the data and are reachable via "show more," never hidden from
 * the underlying count.
 */
export function DashboardSection({
  title,
  description,
  items,
  cap,
  emptyTitle = "Nothing here right now",
}: {
  title: string;
  description?: string;
  items: MorningPlanItem[];
  cap?: number;
  emptyTitle?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = cap && !showAll ? items.slice(0, cap) : items;
  const hiddenCount = cap ? Math.max(0, items.length - cap) : 0;

  return (
    <Card role="region" aria-label={title}>
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-medium text-black dark:text-zinc-50">
          {title}
          {cap && items.length > 0 && (
            <span className="ml-2 text-xs font-normal text-zinc-500 dark:text-zinc-400">
              ({items.length} total, showing {Math.min(cap, items.length)})
            </span>
          )}
        </h2>
      </div>
      {description && (
        <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">{description}</p>
      )}

      {items.length === 0 ? (
        <PageState variant="no-action" title={emptyTitle} />
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map((item) => (
            <DashboardCard key={item.id} item={item} />
          ))}
        </ul>
      )}

      {hiddenCount > 0 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-3 text-xs font-medium text-zinc-600 underline hover:text-black dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          Show {hiddenCount} more
        </button>
      )}
    </Card>
  );
}
