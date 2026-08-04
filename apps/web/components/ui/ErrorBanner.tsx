import { ApiError } from "@/lib/api/client";

const DEFAULT_MESSAGES: Record<number, string> = {
  400: "The request couldn't be completed as sent.",
  404: "Not found.",
  422: "The submitted data didn't pass validation.",
  429: "Rate limit exceeded — wait a few seconds and try again.",
  503: "This feature isn't available right now (missing configuration).",
};

/**
 * Centralizes status-code -> message mapping (ADR-029) since 400/404/422/
 * 429/503 recur across the ask/orders/strategy flows with mostly-generic-
 * but-sometimes-endpoint-specific copy. Pass `messages` to override the
 * default text for a given status in one call site (e.g. the ask page's
 * 429/503 copy).
 */
export function ErrorBanner({
  error,
  messages,
}: {
  error: unknown;
  messages?: Partial<Record<number, string>>;
}) {
  if (!error) return null;

  let text: string;
  if (error instanceof ApiError) {
    text = messages?.[error.status] ?? DEFAULT_MESSAGES[error.status] ?? error.message;
  } else if (error instanceof Error) {
    text = error.message;
  } else {
    text = "Something went wrong.";
  }

  return (
    <div
      role="alert"
      className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
    >
      {text}
    </div>
  );
}
