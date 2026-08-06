/**
 * ORDER AUTHORITY (PROJECT_INSTRUCTIONS.md v2 amendment, OA-3/OA-5):
 * flags an order/recommendation that cannot proceed without an explicit
 * human confirmation. Text-labeled, not a bare color dot.
 */
export function ApprovalRequiredBadge({ expiresAt }: { expiresAt?: string }) {
  return (
    <span
      role="status"
      className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-950 dark:text-blue-300"
    >
      <span aria-hidden="true">&#9998;</span>
      Approval required
      {expiresAt ? (
        <span className="font-normal opacity-80">&middot; expires {expiresAt}</span>
      ) : null}
    </span>
  );
}
