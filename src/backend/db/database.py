import aiosqlite
import redis.asyncio as aioredis
from typing import AsyncGenerator, Optional
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


async def init_sqlite_db(db_path: Optional[str] = None) -> None:
    """
    Creates SQLite tables for durable execution trace history and token spend logs.
    """
    path = db_path or settings.SQLITE_DB_PATH
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        
        # Execution Trace Records Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trace_records (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                parent_agent_id TEXT,
                status TEXT NOT NULL,
                goal TEXT NOT NULL,
                model TEXT NOT NULL,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trace_data JSON NOT NULL
            );
        """)
        
        # Token Spend Ledger Table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS token_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        await db.commit()


async def get_sqlite_db(db_path: Optional[str] = None) -> AsyncGenerator[aiosqlite.Connection, None]:
    """
    Async generator providing SQLite database connection for FastAPI dependency injection or direct use.
    """
    path = db_path or settings.SQLITE_DB_PATH
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        yield db
