import { LoadingSpinner } from "./LoadingSpinner";

export type PageStateVariant =
  | "empty"
  | "loading"
  | "stale"
  | "disconnected"
  | "permission"
  | "market-closed"
  | "no-action";

const VARIANT_COPY: Record<PageStateVariant, { icon: string; defaultTitle: string }> = {
  empty: { icon: "□", defaultTitle: "Nothing here yet" },
  loading: { icon: "", defaultTitle: "Loading" },
  stale: { icon: "!", defaultTitle: "Showing stale data" },
  disconnected: { icon: "⊘", defaultTitle: "Can't reach the API" },
  permission: { icon: "\u{1F512}", defaultTitle: "Not available in this operating mode" },
  "market-closed": { icon: "\u{1F550}", defaultTitle: "Market is closed" },
  "no-action": { icon: "✓", defaultTitle: "Nothing needs your attention" },
};

const VARIANT_ROLE: Record<PageStateVariant, "status" | "alert"> = {
  empty: "status",
  loading: "status",
  stale: "status",
  disconnected: "alert",
  permission: "status",
  "market-closed": "status",
  "no-action": "status",
};

/**
 * One reusable component for every "nothing to render normally" case a
 * placeholder page needs (R2 acceptance criteria: empty, loading, stale,
 * disconnected, permission, market-closed, no-action). Each variant's
 * meaning is carried by its title text, not by color/icon alone.
 */
export function PageState({
  variant,
  title,
  description,
}: {
  variant: PageStateVariant;
  title?: string;
  description?: string;
}) {
  if (variant === "loading") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
        <LoadingSpinner label={title ?? VARIANT_COPY.loading.defaultTitle} />
        {description && (
          <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
        )}
      </div>
    );
  }

  const copy = VARIANT_COPY[variant];
  return (
    <div
      role={VARIANT_ROLE[variant]}
      className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700"
    >
      <span aria-hidden="true" className="text-2xl">
        {copy.icon}
      </span>
      <p className="font-medium text-black dark:text-zinc-50">{title ?? copy.defaultTitle}</p>
      {description && (
        <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
      )}
    </div>
  );
}
