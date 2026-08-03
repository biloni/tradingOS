const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: string;
  time_utc: string;
};

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API health check failed: ${response.status}`);
  }
  return response.json() as Promise<HealthResponse>;
}
