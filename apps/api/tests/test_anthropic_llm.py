"""AnthropicLLMProvider is tested against a mocked anthropic-py Message
response — no network call, no real Anthropic spend, per the project's
fixtures-not-live-APIs test policy (same pattern as
test_alpaca_paper_broker.py)."""

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from tradingos_api.core.config import Settings
from tradingos_api.providers.anthropic_llm import AnthropicLLMProvider
from tradingos_api.providers.llm import LLMProviderNotConfigured


def _settings_with_key() -> Settings:
    return Settings(anthropic_api_key="sk-ant-test-key")


def _fake_message(**overrides: object) -> Message:
    defaults: dict[str, object] = dict(
        id="msg_test",
        content=[TextBlock(type="text", text="hello")],
        model="claude-sonnet-5",
        role="assistant",
        stop_reason="end_turn",
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )
    defaults.update(overrides)
    return Message(**defaults)


class TestConfiguration:
    def test_raises_when_key_missing(self) -> None:
        settings = Settings(anthropic_api_key=None)
        with pytest.raises(LLMProviderNotConfigured):
            AnthropicLLMProvider(settings)


class TestComplete:
    def test_maps_text_only_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AnthropicLLMProvider(_settings_with_key())
        message = _fake_message(content=[TextBlock(type="text", text="AAPL looks bullish.")])
        monkeypatch.setattr(provider._client.messages, "create", lambda **kwargs: message)

        response = provider.complete(
            prompt_version="v1",
            system_prompt="be helpful",
            messages=[{"role": "user", "content": "hi"}],
        )

        assert response.text == "AAPL looks bullish."
        assert response.tool_calls == []
        assert response.stop_reason == "end_turn"
        assert response.model == "claude-sonnet-5"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.raw_content == [
            {"citations": None, "text": "AAPL looks bullish.", "type": "text"}
        ]

    def test_maps_tool_use_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = AnthropicLLMProvider(_settings_with_key())
        message = _fake_message(
            content=[
                ToolUseBlock(
                    type="tool_use", id="toolu_1", name="get_indicators", input={"ticker": "AAPL"}
                )
            ],
            stop_reason="tool_use",
        )
        monkeypatch.setattr(provider._client.messages, "create", lambda **kwargs: message)

        response = provider.complete(
            prompt_version="v1",
            system_prompt="be helpful",
            messages=[{"role": "user", "content": "how's AAPL?"}],
            tools=[{"name": "get_indicators", "description": "d", "input_schema": {}}],
        )

        assert response.text is None
        assert response.stop_reason == "tool_use"
        assert len(response.tool_calls) == 1
        call = response.tool_calls[0]
        assert call.tool_use_id == "toolu_1"
        assert call.tool_name == "get_indicators"
        assert call.arguments == {"ticker": "AAPL"}

    def test_maps_multi_block_response_preserving_raw_content_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = AnthropicLLMProvider(_settings_with_key())
        message = _fake_message(
            content=[
                TextBlock(type="text", text="Let me check."),
                ToolUseBlock(
                    type="tool_use",
                    id="toolu_2",
                    name="get_price_summary",
                    input={"ticker": "SPY"},
                ),
            ],
            stop_reason="tool_use",
        )
        monkeypatch.setattr(provider._client.messages, "create", lambda **kwargs: message)

        response = provider.complete(
            prompt_version="v1",
            system_prompt="be helpful",
            messages=[{"role": "user", "content": "?"}],
        )

        assert response.text == "Let me check."
        assert len(response.tool_calls) == 1
        assert len(response.raw_content) == 2
        assert response.raw_content[0]["type"] == "text"
        assert response.raw_content[1]["type"] == "tool_use"
