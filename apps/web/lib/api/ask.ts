import { apiPost } from "./client";

export type RecommendationSummary = {
  recommendation_id: string;
  ticker: string;
  mode: string;
  lane_action: string | null;
  confidence: string;
  score: string | null;
};

export type AskResponse = {
  answer: string;
  recommendations: RecommendationSummary[];
  model_call_record_ids: string[];
  iterations: number;
};

export function askQuestion(question: string): Promise<AskResponse> {
  return apiPost<AskResponse>("/api/v1/ask", { question });
}
