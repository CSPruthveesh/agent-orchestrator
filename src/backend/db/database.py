import redis.asyncio as aioredis
from typing import Optional
from src.backend.config import settings

# Global Redis Connection Pool Singleton
_redis_pool: Optional[aioredis.ConnectionPool] = None


def get_redis_pool() -> aioredis.ConnectionPool:
    """
    Retrieves or initializes the global Redis connection pool.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_connection_url,
            decode_responses=True,
            max_connections=20
        )
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    """
    Returns an async Redis client instance configured with the active pool.
    """
    pool = get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def close_redis_pool() -> None:
    """
    Gracefully closes the global Redis connection pool.
    """
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
