import { useQuery } from "@tanstack/react-query";
import { listAccounts } from "@/lib/api/accounts";

export function useAccounts() {
  return useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
}

/** Single-user system (ADR-007) — the first account is the only account. */
export function useDefaultAccount() {
  const query = useAccounts();
  return { ...query, data: query.data?.[0] };
}
