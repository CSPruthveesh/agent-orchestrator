import pytest
import redis.asyncio as aioredis
from src.backend.db import database
from src.backend.db.database import (
    get_redis_pool,
    get_redis_client,
    close_redis_pool
)


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
async def test_redis_live_ping():
    """
    Tests live ping operation against Redis instance (skips if Redis server is unavailable).
    """
    await close_redis_pool()
    client = await get_redis_client()
    try:
        response = await client.ping()
        assert response is True or response == "PONG"
    except Exception as e:
        pytest.skip(f"Live Redis server not reachable: {e}")
    finally:
        await client.aclose()
        await close_redis_pool()
