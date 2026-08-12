import os
import pytest
import tempfile
import redis.asyncio as aioredis
from src.backend.db import database
from src.backend.db.database import (
    get_redis_pool,
    get_redis_client,
    close_redis_pool,
    init_sqlite_db
)
from src.backend.db.repository import TraceRepository


@pytest.mark.asyncio
async def test_redis_pool_singleton():
    """
    Asserts that get_redis_pool returns a singleton ConnectionPool instance.
    """
    await close_redis_pool()
    pool1 = get_redis_pool()
    pool2 = get_redis_pool()
    assert pool1 is pool2
    await close_redis_pool()
    assert database._redis_pool is None


@pytest.mark.asyncio
async def test_redis_client_instantiation():
    """
    Asserts that get_redis_client creates an aioredis.Redis instance bound to the pool.
    """
    await close_redis_pool()
    client = await get_redis_client()
    assert isinstance(client, aioredis.Redis)
    assert client.connection_pool is get_redis_pool()
    await client.aclose()
    await close_redis_pool()


@pytest.mark.asyncio
async def test_sqlite_init_and_trace_repository():
    """
    Tests SQLite database initialization and TraceRepository CRUD operations.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initialize tables
        await init_sqlite_db(db_path)
        repo = TraceRepository(db_path)

        # Test log token usage
        await repo.log_token_usage(
            agent_id="agent-123",
            step_id="step-1",
            model="gemini-2.5-flash",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.002
        )

        cost = await repo.get_agent_total_cost("agent-123")
        assert cost == 0.002

        # Test save & get trace
        await repo.save_trace(
            trace_id="trace-123",
            agent_id="agent-123",
            status="COMPLETED",
            goal="Scrape website",
            model="gemini-2.5-flash",
            total_tokens=150,
            total_cost_usd=0.002,
            duration_ms=1200,
            trace_data={"steps": []}
        )

        record = await repo.get_trace("trace-123")
        assert record is not None
        assert record["agent_id"] == "agent-123"
        assert record["status"] == "COMPLETED"
        assert record["total_tokens"] == 150
        assert record["trace_data"] == {"steps": []}

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
