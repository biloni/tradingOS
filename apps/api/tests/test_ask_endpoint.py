"""`/api/v1/ask` endpoint tests run against an in-memory SQLite database and
a fake LLMProvider — no live Postgres, no real Anthropic call, per the
project's fixtures-not-live-APIs test policy."""

from collections.abc import Generator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import tradingos_api.routers.ask as ask_router
from tradingos_api.core import dependencies as deps_module
from tradingos_api.core.config import Settings
from tradingos_api.core.dependencies import get_llm_provider
from tradingos_api.core.rate_limit import TokenBucketRateLimiter
from tradingos_api.db.base import Base
from tradingos_api.db.session import get_db
from tradingos_api.main import app
from tradingos_api.providers.llm import LLMResponse


class FakeLLMProvider:
    def complete(
        self,
        prompt_version: str,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            prompt_version=prompt_version,
            model="claude-sonnet-5",
            stop_reason="end_turn",
            text="Fake grounded answer.",
            tool_calls=[],
            raw_content=[{"type": "text", "text": "Fake grounded answer."}],
            input_tokens=10,
            output_tokens=5,
        )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


class TestAskEndpoint:
    def test_happy_path_returns_grounded_answer(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_router, "ask_rate_limiter", TokenBucketRateLimiter(capacity=5, refill_per_second=1)
        )
        response = client.post("/api/v1/ask", json={"question": "What does AAPL look like?"})
        assert response.status_code == 200
        assert response.json()["answer"] == "Fake grounded answer."

    def test_blank_question_is_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_router, "ask_rate_limiter", TokenBucketRateLimiter(capacity=5, refill_per_second=1)
        )
        response = client.post("/api/v1/ask", json={"question": ""})
        assert response.status_code == 422

    def test_rate_limit_returns_429_once_bucket_is_exhausted(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            ask_router, "ask_rate_limiter", TokenBucketRateLimiter(capacity=1, refill_per_second=0)
        )
        first = client.post("/api/v1/ask", json={"question": "one"})
        second = client.post("/api/v1/ask", json={"question": "two"})

        assert first.status_code == 200
        assert second.status_code == 429


class TestGetLlmProviderDependency:
    def test_missing_api_key_raises_a_503_not_a_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(deps_module, "get_settings", lambda: Settings(anthropic_api_key=None))

        with pytest.raises(HTTPException) as exc_info:
            deps_module.get_llm_provider()

        assert exc_info.value.status_code == 503
