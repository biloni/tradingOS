import { useQuery } from "@tanstack/react-query";
import { getOperatingMode } from "@/lib/api/operatingMode";

/**
 * The one hook every environment-banner/operating-mode-status component
 * must use — do not read this value from `localStorage`, a cookie, a URL
 * query param, or any other client-side source (R2 acceptance criterion:
 * "whose display value comes from the API, not client storage").
 */
export function useOperatingMode() {
  return useQuery({
    queryKey: ["operating-mode"],
    queryFn: getOperatingMode,
    staleTime: 30_000,
  });
}
