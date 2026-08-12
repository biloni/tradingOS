"use client";

import { useState, type FormEvent } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAskQuestion } from "@/lib/hooks/useAsk";
import type { RecommendationSummary } from "@/lib/api/ask";

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; recommendations: RecommendationSummary[] };

// /api/v1/ask is stateless per request (ADR-019) — this page keeps its own
// local display history rather than needing a backend Conversation table.
const ASK_ERROR_MESSAGES: Partial<Record<number, string>> = {
  429: "You're asking questions faster than the configured limit — wait a few seconds and try again.",
  503: "Natural-language query isn't available right now (no Anthropic API key configured in this environment).",
  422: "Questions must be between 1 and 2000 characters.",
};

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const ask = useAskQuestion();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuestion("");

    ask.mutate(trimmed, {
      onSuccess: (response) => {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: response.answer,
            recommendations: response.recommendations,
          },
        ]);
      },
    });
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Ask
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Natural-language questions grounded in tool results only — the model never invents a
          price or a score (principles 6/7). Try: &ldquo;What does AAPL&apos;s current setup look
          like?&rdquo;
        </p>
      </div>

      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-4">
          {messages.length === 0 && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No messages yet.</p>
          )}
          {messages.map((message, index) => (
            <div
              key={index}
              className={`rounded-lg px-4 py-3 text-sm ${
                message.role === "user"
                  ? "ml-auto max-w-lg bg-black text-white dark:bg-zinc-50 dark:text-black"
                  : "mr-auto max-w-2xl bg-zinc-100 text-black dark:bg-zinc-800 dark:text-zinc-50"
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {message.role === "assistant" && message.recommendations.length > 0 && (
                <div className="mt-3 flex flex-col gap-2 border-t border-zinc-300 pt-3 dark:border-zinc-700">
                  {message.recommendations.map((rec) => (
                    <div key={rec.recommendation_id} className="flex items-center gap-2 text-xs">
                      <span className="font-medium">{rec.ticker}</span>
                      {rec.lane_action && <span>{rec.lane_action}</span>}
                      {rec.score && <span>score {rec.score}</span>}
                      <StatusPill status={rec.confidence} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {ask.isPending && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Thinking…</p>
          )}
        </div>

        <ErrorBanner error={ask.error} messages={ASK_ERROR_MESSAGES} />

        <form onSubmit={handleSubmit} className="flex gap-2">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about the tracked symbols…"
            rows={2}
            className="flex-1"
          />
          <Button type="submit" disabled={ask.isPending || !question.trim()}>
            Send
          </Button>
        </form>
      </Card>
    </div>
  );
}
