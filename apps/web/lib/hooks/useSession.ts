import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSessionStatus, login, logout, stepUp } from "@/lib/api/auth";

export const SESSION_QUERY_KEY = ["auth", "session"];

/**
 * `GET /api/v1/auth/session` never 401s (Revision Prompt 16, ADR-066: it's
 * the one route the frontend can always call to find out whether to show
 * a login screen), so `authenticated: false` is a normal successful
 * response here, not an error state — components should branch on
 * `data.authenticated`, not `isError`.
 */
export function useSession() {
  return useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: getSessionStatus,
    staleTime: 30_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => login(password),
    onSuccess: (data) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, data);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    onSuccess: (data) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, data);
      // Every other query may hold data fetched under the now-revoked
      // session — drop it all so a re-login doesn't show stale caches.
      // (Compare by key[0], not array identity: react-query may not
      // preserve reference equality with the SESSION_QUERY_KEY constant.)
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
    },
  });
}

export function useStepUp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => stepUp(password),
    onSuccess: (data) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, data);
    },
  });
}
