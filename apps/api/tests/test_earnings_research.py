"""`services/earnings_research.py` + `POST /api/v1/earnings-research` —
the `pause_turn` continuation loop, citation extraction, and the
endpoint's rate limit / validation / degradation behavior. All against a
fake `LLMProvider` (service-level tests) or `app.dependency_overrides`
(endpoint-level tests) — no network call, no real Anthropic spend, no
real web search. Live verification against the real API lives in
`docs/TEST_EVIDENCE.md`."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import earnings_research_rate_limiter
from tradingos_api.main import app
from tradingos_api.providers.llm import LLMResponse
from tradingos_api.services.earnings_research import (
    MAX_PAUSE_CONTINUATIONS,
    research_company,
)


def _text_block(text: str, citations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "text", "text": text}
    if citations is not None:
        block["citations"] = citations
    return block


class _OneShotLLM:
    """No `pause_turn` — the server-side search loop finished within a
    single call, as it does the overwhelming majority of the time."""

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raw = [
            _text_block("MRVL reports on 2026-12-01.", citations=[{"url": "https://a.example/1"}]),
            _text_block(
                "Consensus EPS is $1.35.",
                citations=[{"url": "https://a.example/2", "title": "Estimates"}],
            ),
        ]
        return LLMResponse(
            prompt_version="earnings-research-v1",
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="MRVL reports on 2026-12-01.\nConsensus EPS is $1.35.",
            tool_calls=[],
            raw_content=raw,
            input_tokens=500,
            output_tokens=200,
        )


class _PauseThenDoneLLM:
    """Simulates a real, documented server-tool behavior
    (`shared/tool-use-concepts.md`): the search loop hits its own
    internal iteration cap and returns `stop_reason: pause_turn`;
    resending the conversation with the paused turn appended resumes it."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    def complete(
        self, prompt_version: str, system_prompt: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> LLMResponse:
        self.calls.append(messages)
        if len(self.calls) == 1:
            return LLMResponse(
                prompt_version=prompt_version,
                model="claude-sonnet-5",
                stop_reason="pause_turn",
                text=None,
                tool_calls=[],
                raw_content=[{"type": "server_tool_use", "id": "srvtoolu_1"}],
                input_tokens=300,
                output_tokens=100,
            )
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="Resumed and completed the report.",
            tool_calls=[],
            raw_content=[_text_block("Resumed and completed the report.")],
            input_tokens=400,
            output_tokens=150,
        )


class _AlwaysPauseLLM:
    """Never stops pausing — proves the continuation budget actually
    bounds the loop rather than looping forever."""

    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            prompt_version="earnings-research-v1",
            model="claude-sonnet-5",
            stop_reason="pause_turn",
            text=None,
            tool_calls=[],
            raw_content=[{"type": "server_tool_use", "id": "srvtoolu_x"}],
            input_tokens=100,
            output_tokens=50,
        )


class _NoCitationsLLM:
    def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            prompt_version="earnings-research-v1",
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="Could not verify this company via search.",
            tool_calls=[],
            raw_content=[_text_block("Could not verify this company via search.")],
            input_tokens=200,
            output_tokens=50,
        )


class TestResearchCompanyService:
    def test_single_call_extracts_deduplicated_citations(self, db_session: Session) -> None:
        result = research_company(db_session, _OneShotLLM(), "Marvell Technology")
        assert result.iterations == 1
        assert "MRVL" in result.answer
        assert [s.url for s in result.sources] == ["https://a.example/1", "https://a.example/2"]
        assert result.sources[1].title == "Estimates"
        assert len(result.model_call_record_ids) == 1

    def test_pause_turn_resumes_with_the_paused_turn_appended(self, db_session: Session) -> None:
        llm = _PauseThenDoneLLM()
        result = research_company(db_session, llm, "Marvell Technology")
        assert result.iterations == 2
        assert result.answer == "Resumed and completed the report."
        assert len(llm.calls) == 2
        # second call's messages must include the first (paused) assistant turn
        assert llm.calls[1][-1]["role"] == "assistant"
        assert llm.calls[1][-1]["content"] == [{"type": "server_tool_use", "id": "srvtoolu_1"}]

    def test_pause_turn_budget_is_actually_bounded(self, db_session: Session) -> None:
        result = research_company(db_session, _AlwaysPauseLLM(), "Marvell Technology")
        assert result.iterations == MAX_PAUSE_CONTINUATIONS + 1
        assert "continuation budget" in result.answer

    def test_no_citations_is_not_an_error(self, db_session: Session) -> None:
        result = research_company(db_session, _NoCitationsLLM(), "Not A Real Company")
        assert result.sources == []
        assert "Could not verify" in result.answer


def _override_llm(fake_llm: Any) -> None:
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm


class TestEarningsResearchEndpoint:
    def test_answers_with_sources(self, client: TestClient) -> None:
        earnings_research_rate_limiter.reset()
        _override_llm(_OneShotLLM())
        try:
            response = client.post(
                "/api/v1/earnings-research", json={"company": "Marvell Technology"}
            )
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)

        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["sources"]) == 2
        assert body["iterations"] == 1

    def test_blank_company_is_rejected(self, client: TestClient) -> None:
        earnings_research_rate_limiter.reset()
        response = client.post("/api/v1/earnings-research", json={"company": ""})
        assert response.status_code == 422

    def test_rate_limit_returns_429(self, client: TestClient) -> None:
        earnings_research_rate_limiter.reset()
        _override_llm(_OneShotLLM())
        try:
            for _ in range(3):
                ok_response = client.post(
                    "/api/v1/earnings-research", json={"company": "Marvell Technology"}
                )
                assert ok_response.status_code == 200
            limited_response = client.post(
                "/api/v1/earnings-research", json={"company": "Marvell Technology"}
            )
        finally:
            app.dependency_overrides.pop(get_llm_provider, None)
            earnings_research_rate_limiter.reset()

        assert limited_response.status_code == 429
