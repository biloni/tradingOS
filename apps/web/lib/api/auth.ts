import { apiGet, apiPost } from "./client";

/**
 * Mirrors `schemas/auth.py::SessionStatusResponse` (Revision Prompt 16,
 * ADR-066). `expires_at` is only present when `authenticated` is true.
 */
export type SessionStatusResponse = {
  authenticated: boolean;
  stepped_up: boolean;
  expires_at?: string | null;
};

export function login(password: string): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>("/api/v1/auth/login", { password });
}

export function logout(): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>("/api/v1/auth/logout");
}

export function getSessionStatus(): Promise<SessionStatusResponse> {
  return apiGet<SessionStatusResponse>("/api/v1/auth/session");
}

export function stepUp(password: string): Promise<SessionStatusResponse> {
  return apiPost<SessionStatusResponse>("/api/v1/auth/step-up", { password });
}
