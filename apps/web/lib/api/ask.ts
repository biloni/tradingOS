import { apiPost } from "./client";

export type RecommendationSummary = {
  recommendation_id: number;
  symbol_ticker: string;
  score: string;
  confidence: string;
  signal_breakdown: Record<string, number>;
};

export type AskResponse = {
  answer: string;
  recommendations: RecommendationSummary[];
  llm_call_log_ids: number[];
  iterations: number;
};

export function askQuestion(question: string): Promise<AskResponse> {
  return apiPost<AskResponse>("/api/v1/ask", { question });
}
