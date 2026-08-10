import { apiGet } from "./client";

export type Account = {
  id: string;
  account_type: string;
  name: string;
  base_currency: string;
  is_active: boolean;
};

export function listAccounts(): Promise<Account[]> {
  return apiGet<Account[]>("/api/v1/portfolio/accounts");
}
