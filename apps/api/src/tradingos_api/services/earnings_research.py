"""On-demand earnings-research agent (`POST /api/v1/earnings-research`) —
tracks upcoming earnings for any current S&P 500, Dow Jones Industrial
Average, or Nasdaq-100 company and produces an educational earnings
projection + investment-quality checklist, grounded in Anthropic's
server-side `web_search` tool rather than this app's own (much smaller)
tracked-instrument universe.

Architecturally distinct from `services/ask.py` and
`services/committee_orchestrator.py`: those use *client-defined* tools —
the model calls a tool, this process executes it against our own
database, and the result is fed back as a `tool_result` block in a loop
this code drives. `web_search` is a *server-side* tool — Anthropic
executes the search and splices the result directly into the same
response, in the same API call, with no round trip through this
process. The only loop this module owns is the documented `pause_turn`
continuation (`shared/tool-use-concepts.md`): if the server-side search
loop hits its own internal iteration cap mid-turn, the response comes
back with `stop_reason: "pause_turn"` and must be resumed by resending
the conversation with the paused assistant turn appended — never by
injecting a "continue" message, which the API already knows to ignore
in favor of the trailing `server_tool_use` block."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from tradingos_api.models.operations import ModelCallRecord
from tradingos_api.providers.llm import LLMProvider
from tradingos_api.schemas.earnings_research import EarningsResearchResponse, ResearchSource
from tradingos_api.services.llm_cost import estimate_cost_usd

PROMPT_VERSION = "earnings-research-v1"
MAX_PAUSE_CONTINUATIONS = 3
MAX_SEARCH_USES = 6

SYSTEM_PROMPT = """You are the "Earnings Research" assistant inside a personal, \
paper-trading-only decision-support tool. You research one company at a time, \
on request, using live web search.

Hard rules, no exceptions:
- This is educational research, never investment advice. Never tell the user \
to buy, sell, or hold anything. End every report with a plain statement that \
this is educational only and a human must decide.
- You never place, modify, or cancel any order. This tool has no live trading \
capability.
- Before researching, use web search to confirm the company is a current \
constituent of the S&P 500, the Dow Jones Industrial Average, or the \
Nasdaq-100. You are not limited to any particular pre-set list of companies — \
verify current index membership by searching, not from memory (index \
membership changes over time and your training data may be stale). If the \
company is not a current constituent of any of the three, or you cannot \
verify it, say so plainly and do not fabricate a report for it.
- Every figure you state (a price, an estimate, a growth rate, a date) must \
come from a web search result you actually retrieved in this conversation. \
Never estimate or recall a number from training data — search for it, and if \
you can't find a reliable current source, say the figure is unavailable \
rather than guessing.
- Cite your sources. When you state a fact from a search result, the citation \
should be attached to that sentence.

Structure every report as:
1. A one-line identification: company name, ticker, which index/indices it \
belongs to, and its next confirmed or estimated earnings date.
2. A concise Markdown table of current estimates: consensus EPS, consensus \
revenue, prior-year actuals for comparison, and analyst estimate count if \
available.
3. A concise Markdown table comparing current valuation (P/E or other \
relevant multiple) against the company's own trailing history and its sector \
peers, with a one-line takeaway per row.
4. A short "Key catalysts" list — concrete, sourced, near-term events or \
trends that could move the stock.
5. A short "Key risks" list — concrete, sourced, near-term risks.
6. A plain-English, non-advisory risk/reward summary paragraph: what would \
have to go right for this to be a strong quarter, what would have to go \
wrong, stated as an educational framing exercise, not a recommendation.
7. A "Sources" list of every URL you cited.

State plainly whenever a figure or fact could not be found via search, rather \
than filling the gap."""


def _extract_sources(raw_content: list[dict[str, Any]]) -> list[ResearchSource]:
    """Web search citations attach to the specific `text` block that cited
    them (`shared/tool-use-concepts.md` — server tools return citations
    inline, not as a separate top-level structure), so sources are
    collected by walking every text block's `citations` array rather than
    looking for one block type. Deduplicated by URL, order preserved."""
    seen: dict[str, ResearchSource] = {}
    for block in raw_content:
        if block.get("type") != "text":
            continue
        for citation in block.get("citations") or []:
            url = citation.get("url")
            if not url or url in seen:
                continue
            seen[url] = ResearchSource(url=url, title=citation.get("title"))
    return list(seen.values())


def _log_call(
    db: Session,
    model: str,
    input_tokens: int,
    output_tokens: int,
    stop_reason: str,
    response_excerpt: str | None,
) -> ModelCallRecord:
    record = ModelCallRecord(
        agent_run_id=None,
        prompt_version_label=PROMPT_VERSION,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost_usd(model, input_tokens, output_tokens),
        stop_reason=stop_reason,
        response_excerpt=(response_excerpt[:500] if response_excerpt else None),
    )
    db.add(record)
    db.flush()
    return record


def research_company(db: Session, llm: LLMProvider, company: str) -> EarningsResearchResponse:
    """Research one company, live, via web search. Stateless per request —
    no conversation history is persisted, matching ADR-019's `/ask`
    precedent (a caller wanting multi-turn follow-up resends context
    itself)."""
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Research {company} for an upcoming-earnings educational report, "
                "following the required structure exactly."
            ),
        }
    ]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCH_USES}]
    model_call_record_ids: list[Any] = []

    response = None
    calls_made = 0
    for _ in range(MAX_PAUSE_CONTINUATIONS + 1):
        calls_made += 1
        response = llm.complete(
            prompt_version=PROMPT_VERSION,
            system_prompt=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )
        record = _log_call(
            db,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
            response_excerpt=response.text,
        )
        model_call_record_ids.append(record.id)

        if response.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": response.raw_content})
    assert response is not None  # loop runs at least once

    db.commit()
    sources = _extract_sources(response.raw_content)
    answer = response.text or (
        "The research agent's web search loop did not finish within its "
        "continuation budget. Please try again with a more specific company name."
    )
    return EarningsResearchResponse(
        answer=answer,
        sources=sources,
        model_call_record_ids=model_call_record_ids,
        iterations=calls_made,
    )
