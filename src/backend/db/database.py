import redis.asyncio as aioredis
import aiosqlite
from typing import Optional
from src.backend.config import settings

# Redis connection pool singleton
_redis_pool: Optional[aioredis.ConnectionPool] = None


async def get_redis_pool() -> aioredis.ConnectionPool:
    """
    Returns or creates the global async Redis connection pool singleton.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_connection_url,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True
        )
    return _redis_pool


async def get_redis_client() -> aioredis.Redis:
    """
    Returns an async Redis client backed by the global connection pool.
    """
    pool = await get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def close_redis_pool() -> None:
    """
    Safely closes the async Redis connection pool.
    """
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None


async def get_sqlite_db(db_path: Optional[str] = None) -> aiosqlite.Connection:
    """
    Returns an opened async SQLite database connection. Caller is responsible for closing it.
    """
    target_path = db_path or settings.SQLITE_DB_PATH
    db = await aiosqlite.connect(target_path)
    db.row_factory = aiosqlite.Row
    return db


async def init_sqlite_db(db_path: Optional[str] = None) -> None:
    """
    Initializes SQLite tables for traces and token ledger if they do not exist.
    """
    target_path = db_path or settings.SQLITE_DB_PATH
    async with aiosqlite.connect(target_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trace_records (
                trace_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                parent_agent_id TEXT,
                status TEXT NOT NULL,
                goal TEXT NOT NULL,
                model TEXT NOT NULL,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0,
                trace_data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS token_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                step_cost_usd REAL NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
