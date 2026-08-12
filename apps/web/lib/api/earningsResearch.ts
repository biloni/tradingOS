import { apiPost } from "./client";

export type ResearchSource = {
  url: string;
  title: string | null;
};

export type EarningsResearchResponse = {
  answer: string;
  sources: ResearchSource[];
  model_call_record_ids: string[];
  iterations: number;
};

export function researchCompany(company: string): Promise<EarningsResearchResponse> {
  return apiPost<EarningsResearchResponse>("/api/v1/earnings-research", { company });
}
