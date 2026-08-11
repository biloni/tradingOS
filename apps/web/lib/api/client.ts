const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Every Numeric-backed field in this API (prices, cash, backtest metrics,
 * indicator values, strategy thresholds) is serialized as a JSON string,
 * never a float — the backend never float-maths currency (ADR-031). The
 * typed response interfaces in this directory type those fields `string`
 * on purpose; convert with `Number(...)` only at the point of display or
 * chart data, never inside the fetch layer.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
    // Revision Prompt 16, ADR-066: the API issues an httpOnly session
    // cookie on login. Cross-origin (localhost:3000 -> localhost:8000)
    // fetch never sends cookies without this, even for same-origin-looking
    // calls in dev — every request needs it, not just ones that already
    // "know" they're authenticated.
    credentials: "include",
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // Response wasn't JSON (or had no body) — fall back to statusText.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}
