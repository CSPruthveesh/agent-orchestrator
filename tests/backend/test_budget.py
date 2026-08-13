import pytest
import redis.asyncio as aioredis
from src.backend.engine.budget_manager import (
    TokenBudgetManager,
    BudgetExceededException
)


def test_cost_calculation():
    """
    Tests static cost calculation logic across model pricing tables.
    """
    manager = TokenBudgetManager()
    # gemini-2.5-flash: $0.075 / 1M prompt, $0.30 / 1M completion
    # 1,000,000 prompt + 1,000,000 completion = $0.375
    cost = manager.calculate_cost(1_000_000, 1_000_000, "gemini-2.5-flash")
    assert pytest.approx(cost, 0.0001) == 0.375


@pytest.mark.asyncio
async def test_budget_recording_and_exception():
    """
    Tests atomic token spend recording in Redis and BudgetExceededException triggering.
    """
    try:
        client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable for budget manager test: {e}")

    manager = TokenBudgetManager(redis_client=client)
    agent_id = "test-budget-agent-001"
    max_budget_usd = 0.05  # $0.05 limit

    try:
        await manager.reset_budget(agent_id)

        # 1. Normal usage within budget
        summary = await manager.record_usage_and_check(
            agent_id=agent_id,
            prompt_tokens=10_000,
            completion_tokens=5_000,
            max_budget_usd=max_budget_usd,
            model="gemini-2.5-flash"
        )
        assert summary["agent_id"] == agent_id
        assert summary["total_spend_usd"] < max_budget_usd
        assert summary["total_tokens"] == 15_000

        # 2. Heavy usage exceeding budget limit -> Must raise BudgetExceededException
        with pytest.raises(BudgetExceededException) as exc_info:
            await manager.record_usage_and_check(
                agent_id=agent_id,
                prompt_tokens=100_000_000,  # Massive token burst
                completion_tokens=50_000_000,
                max_budget_usd=max_budget_usd,
                model="gemini-2.5-flash"
            )

        assert exc_info.value.agent_id == agent_id
        assert exc_info.value.current_spend_usd > max_budget_usd

    finally:
        await manager.reset_budget(agent_id)
        await client.aclose()
