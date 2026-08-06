import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DecisionLaneBadge } from "@/components/ui/DecisionLaneBadge";
import { DataFreshnessBadge } from "@/components/ui/DataFreshnessBadge";
import { EvidenceCompletenessIndicator } from "@/components/ui/EvidenceCompletenessIndicator";
import { ApprovalRequiredBadge } from "@/components/ui/ApprovalRequiredBadge";
import { EventRiskWarning } from "@/components/ui/EventRiskWarning";
import { IncompletePlanBanner } from "@/components/ui/IncompletePlanBanner";
import { SourceTimestamp } from "@/components/ui/SourceTimestamp";
import { OrderStateTimeline } from "@/components/ui/OrderStateTimeline";

/**
 * R2 acceptance criterion: "Accessibility checks cover badges and
 * banners without relying only on color." Every assertion below checks
 * for descriptive *text* content (what a screen reader announces, what
 * a color-blind or grayscale-display user reads) rather than asserting
 * on a CSS color class — a badge that only conveyed meaning through
 * color would fail every one of these.
 */
describe("UI primitive accessibility — text conveys meaning, not just color", () => {
  it("DecisionLaneBadge names the lane in text, with a decorative (aria-hidden) icon", () => {
    render(<DecisionLaneBadge lane="INVESTMENT" />);
    expect(screen.getByText("Investment")).toBeInTheDocument();
    const icon = screen.getByText("◆");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("DataFreshnessBadge names STALE in text, not just a color change", () => {
    render(<DataFreshnessBadge status="STALE" asOf="06:08" />);
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("EvidenceCompletenessIndicator has an accessible name summarizing the count", () => {
    render(<EvidenceCompletenessIndicator available={3} total={5} missingCategories={["News"]} />);
    expect(screen.getByRole("status", { name: "3 of 5 evidence categories available" })).toBeInTheDocument();
    expect(screen.getByText(/Missing: News/)).toBeInTheDocument();
  });

  it("ApprovalRequiredBadge states the requirement in text", () => {
    render(<ApprovalRequiredBadge expiresAt="06:40" />);
    expect(screen.getByText("Approval required")).toBeInTheDocument();
  });

  it("EventRiskWarning explains the stop-is-not-a-guarantee caveat in text", () => {
    render(<EventRiskWarning eventLabel="Earnings tomorrow" />);
    expect(screen.getByText(/Event risk: Earnings tomorrow/)).toBeInTheDocument();
    expect(screen.getByText(/not a guarantee of the stop price/)).toBeInTheDocument();
  });

  it("IncompletePlanBanner is an alert with explicit reason text", () => {
    render(<IncompletePlanBanner reasons={["Fundamentals vendor unavailable"]} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This plan is INCOMPLETE");
    expect(screen.getByText("Fundamentals vendor unavailable")).toBeInTheDocument();
  });

  it("SourceTimestamp renders source, timestamp, and freshness as plain text", () => {
    render(<SourceTimestamp source="Alpaca" timestamp="2026-08-06T06:08:00-07:00" freshness="STALE" />);
    expect(screen.getByText(/Alpaca/)).toHaveTextContent("(stale)");
  });

  it("OrderStateTimeline announces each step's status via visually-hidden text, not color alone", () => {
    render(
      <OrderStateTimeline
        steps={[
          { label: "Draft", status: "done" },
          { label: "Approved", status: "current" },
          { label: "Filled", status: "pending" },
        ]}
      />,
    );
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("(done)")).toBeInTheDocument();
    expect(screen.getByText("(current)")).toBeInTheDocument();
    expect(screen.getByText("(pending)")).toBeInTheDocument();
  });
});
