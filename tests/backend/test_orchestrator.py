import os
import pytest
import tempfile
import redis.asyncio as aioredis

from src.backend.db.database import init_sqlite_db
from src.backend.db.repository import TraceRepository
from src.backend.engine.models import AgentConfig, AgentStatus
from src.backend.engine.orchestrator import AsyncTaskGraphEngine
from src.backend.engine.budget_manager import BudgetExceededException


@pytest.mark.asyncio
async def test_orchestrator_successful_run():
    """
    Tests complete execution of an agent task graph loop with Redis checkpointing and SQLite trace persistence.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_sqlite_db(db_path)
        trace_repo = TraceRepository(db_path)

        try:
            client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
            await client.ping()
        except Exception as e:
            pytest.skip(f"Redis not reachable for orchestrator test: {e}")

        engine = AsyncTaskGraphEngine(redis_client=client, trace_repo=trace_repo)
        config = AgentConfig(
            goal="Test Orchestrator Workflow",
            model="gemini-2.5-flash",
            max_budget_usd=1.00
        )

        state = await engine.execute_agent_loop(config)

        assert state.status == AgentStatus.COMPLETED
        assert len(state.history) >= 2
        assert state.accumulated_tokens > 0
        assert state.accumulated_cost_usd > 0

        # Verify trace saved in SQLite
        checkpoint = await engine.checkpointer.load_checkpoint(config.agent_id)
        assert checkpoint is not None
        assert checkpoint.status == AgentStatus.COMPLETED

        await engine.checkpointer.delete_checkpoint(config.agent_id)
        await client.aclose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_orchestrator_budget_exceeded():
    """
    Tests that setting a tight budget forces immediate agent termination with BudgetExceededException.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        await init_sqlite_db(db_path)
        trace_repo = TraceRepository(db_path)

        try:
            client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
            await client.ping()
        except Exception as e:
            pytest.skip(f"Redis not reachable for budget test: {e}")

        engine = AsyncTaskGraphEngine(redis_client=client, trace_repo=trace_repo)
        # Set practically 0 budget ($0.000001)
        config = AgentConfig(
            goal="Test Budget Exceeded Flow",
            model="gemini-2.5-flash",
            max_budget_usd=0.000001
        )

        with pytest.raises(BudgetExceededException):
            await engine.execute_agent_loop(config)

        # Checkpoint should reflect BUDGET_EXCEEDED status
        checkpoint = await engine.checkpointer.load_checkpoint(config.agent_id)
        assert checkpoint is not None
        assert checkpoint.status == AgentStatus.BUDGET_EXCEEDED

        await engine.checkpointer.delete_checkpoint(config.agent_id)
        await client.aclose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
