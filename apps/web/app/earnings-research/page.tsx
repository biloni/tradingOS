"use client";

import { useState, type FormEvent } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { useEarningsResearch } from "@/lib/hooks/useEarningsResearch";
import type { ResearchSource } from "@/lib/api/earningsResearch";

const RESEARCH_ERROR_MESSAGES: Partial<Record<number, string>> = {
  429: "You're requesting research faster than the configured limit — wait a few seconds and try again.",
  503: "Earnings research isn't available right now (no Anthropic API key configured in this environment).",
  422: "Enter a company name or ticker (1–200 characters).",
};

type ResearchResult = {
  company: string;
  answer: string;
  sources: ResearchSource[];
};

export default function EarningsResearchPage() {
  const [company, setCompany] = useState("");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const research = useEarningsResearch();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = company.trim();
    if (!trimmed) return;

    research.mutate(trimmed, {
      onSuccess: (response) => {
        setResult({ company: trimmed, answer: response.answer, sources: response.sources });
      },
    });
  }

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Earnings Research
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Live web research on any current S&amp;P 500, Dow Jones Industrial Average, or
          Nasdaq-100 company&apos;s upcoming earnings — not limited to a fixed ticker list.
          Educational only, grounded in cited sources, never investment advice.
        </p>
      </div>

      <Card className="flex flex-col gap-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Company name or ticker, e.g. Marvell Technology or MRVL"
            className="flex-1"
          />
          <Button type="submit" disabled={research.isPending || !company.trim()}>
            Research
          </Button>
        </form>

        <ErrorBanner error={research.error} messages={RESEARCH_ERROR_MESSAGES} />

        {research.isPending && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Researching&hellip; this can take up to a minute while sources are searched.
          </p>
        )}

        {result && (
          <div className="flex flex-col gap-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            <h2 className="text-sm font-semibold text-black dark:text-zinc-50">
              {result.company}
            </h2>
            <p className="whitespace-pre-wrap text-sm text-black dark:text-zinc-50">
              {result.answer}
            </p>
            {result.sources.length > 0 && (
              <div className="flex flex-col gap-1 border-t border-zinc-200 pt-3 text-xs dark:border-zinc-800">
                <span className="font-medium text-zinc-600 dark:text-zinc-400">Sources</span>
                <ul className="flex flex-col gap-1">
                  {result.sources.map((source) => (
                    <li key={source.url}>
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-700 underline dark:text-blue-400"
                      >
                        {source.title ?? source.url}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Educational research only — not investment advice. A human must decide.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
