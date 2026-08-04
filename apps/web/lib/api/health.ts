import { apiGet } from "./client";

export type HealthResponse = {
  status: string;
  time_utc: string;
};

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
