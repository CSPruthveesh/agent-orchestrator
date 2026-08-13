import pytest
from src.backend.llm.gateway import AsyncLLMGateway


@pytest.mark.asyncio
async def test_llm_gateway_mock_fallback():
    """
    Asserts that AsyncLLMGateway falls back to mock provider when no API keys are configured.
    """
    gateway = AsyncLLMGateway(gemini_api_key=None, openai_api_key=None)
    res = await gateway.generate_reasoning_step("Analyze execution graph for optimization")

    assert "text" in res
    assert "prompt_tokens" in res
    assert "completion_tokens" in res
    assert res["model"] == "gemini-2.5-flash"
    assert res["provider"] == "mock-simulation"
    assert res["prompt_tokens"] > 0
    assert res["completion_tokens"] > 0


@pytest.mark.asyncio
async def test_llm_gateway_custom_model():
    """
    Asserts that AsyncLLMGateway respects model selection parameter.
    """
    gateway = AsyncLLMGateway()
    res = await gateway.generate_reasoning_step(
        prompt="Synthesize research data",
        model="gemini-1.5-flash"
    )

    assert res["model"] == "gemini-1.5-flash"
    assert "Simulated Gemini reasoning" in res["text"]
