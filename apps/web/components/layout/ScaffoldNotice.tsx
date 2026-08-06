/**
 * Every new Revision Prompt R2 route renders this so it's never mistaken
 * for a finished, data-backed feature. R2's own scope explicitly
 * excludes provider calls, strategy calculations, recommendations,
 * scheduling, and broker submission — every number/name below this
 * notice on these pages is synthetic.
 */
export function ScaffoldNotice({ children }: { children?: React.ReactNode }) {
  return (
    <div
      role="note"
      className="rounded-md border border-dashed border-zinc-300 bg-zinc-50 px-4 py-3 text-sm text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400"
    >
      <span className="font-medium text-zinc-800 dark:text-zinc-200">Scaffold page (Revision Prompt R2).</span>{" "}
      {children ?? "Synthetic placeholder content only — no live data, no provider calls, no orders can be submitted."}
    </div>
  );
}
