import os
import pytest
import tempfile
import redis.asyncio as aioredis

from src.backend.db.database import init_sqlite_db
from src.backend.db.repository import TraceRepository
from src.backend.engine.models import AgentConfig, AgentStatus
from src.backend.engine.orchestrator import AsyncTaskGraphEngine
from src.backend.engine.fanout import MultiAgentFanOutManager


@pytest.mark.asyncio
async def test_multi_agent_fanout_execution():
    """
    Tests supervisor agent spawning 3 worker sub-tasks in parallel and aggregating results via asyncio.gather().
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
            pytest.skip(f"Redis not reachable for fan-out test: {e}")

        orchestrator = AsyncTaskGraphEngine(redis_client=client, trace_repo=trace_repo)
        fanout_manager = MultiAgentFanOutManager(orchestrator=orchestrator, redis_client=client)

        supervisor_id = "supervisor-agent-001"
        subtask_configs = [
            AgentConfig(goal="Scrape product listings", model="gemini-2.5-flash", max_budget_usd=0.50),
            AgentConfig(goal="Analyze pricing trends", model="gemini-2.5-flash", max_budget_usd=0.50),
            AgentConfig(goal="Synthesize summary report", model="gemini-2.5-flash", max_budget_usd=0.50)
        ]

        # Execute fan-out sub-tasks concurrently
        worker_states = await fanout_manager.fan_out_subtasks(
            supervisor_id=supervisor_id,
            subtask_configs=subtask_configs
        )

        assert len(worker_states) == 3
        for state in worker_states:
            assert state.parent_agent_id == supervisor_id
            assert state.status == AgentStatus.COMPLETED

        await client.aclose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
