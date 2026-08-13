import pytest
import redis.asyncio as aioredis
from src.backend.engine.models import (
    AgentState,
    AgentStatus,
    ExecutionStep,
    StepNodeType
)
from src.backend.engine.state_machine import RedisStateCheckpointer


@pytest.mark.asyncio
async def test_checkpoint_save_and_load():
    """
    Tests saving an AgentState to Redis and deserializing it back cleanly.
    """
    # Use fake/mock memory client or active client
    try:
        client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not available for state machine test: {e}")

    checkpointer = RedisStateCheckpointer(redis_client=client, ttl_seconds=60)
    agent_id = "test-agent-checkpoint-001"

    try:
        # Construct agent state
        state = AgentState(
            agent_id=agent_id,
            status=AgentStatus.RUNNING,
            current_step_index=2,
            accumulated_tokens=450,
            accumulated_cost_usd=0.009,
            context_data={"target_url": "https://example.com"}
        )

        step = ExecutionStep(
            agent_id=agent_id,
            node_type=StepNodeType.TOOL_EXECUTION,
            prompt_tokens=300,
            completion_tokens=150,
            step_cost_usd=0.009,
            duration_ms=45
        )
        state.history.append(step)

        # Save checkpoint
        await checkpointer.save_checkpoint(state)

        # Load checkpoint
        loaded = await checkpointer.load_checkpoint(agent_id)
        assert loaded is not None
        assert loaded.agent_id == agent_id
        assert loaded.status == AgentStatus.RUNNING
        assert loaded.current_step_index == 2
        assert loaded.accumulated_tokens == 450
        assert loaded.accumulated_cost_usd == 0.009
        assert loaded.context_data == {"target_url": "https://example.com"}
        assert len(loaded.history) == 1
        assert loaded.history[0].node_type == StepNodeType.TOOL_EXECUTION

        # Verify key exists in active list
        active_ids = await checkpointer.list_active_agent_ids()
        assert agent_id in active_ids

    finally:
        await checkpointer.delete_checkpoint(agent_id)
        await client.aclose()
