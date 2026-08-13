import json
import aiosqlite
from typing import Dict, Any, Optional
from src.backend.config import settings


class TraceRepository:
    """
    Async repository for persisting finish trace logs and token spend ledger entries into SQLite.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.SQLITE_DB_PATH

    async def save_trace(
        self,
        trace_id: str,
        agent_id: str,
        status: str,
        goal: str,
        model: str,
        total_tokens: int,
        total_cost_usd: float,
        duration_ms: int,
        trace_data: Dict[str, Any],
        parent_agent_id: Optional[str] = None
    ) -> None:
        """
        Inserts or replaces an agent execution trace record in SQLite.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO trace_records (
                    trace_id, agent_id, parent_agent_id, status, goal, model,
                    total_tokens, total_cost_usd, duration_ms, trace_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    agent_id,
                    parent_agent_id,
                    status,
                    goal,
                    model,
                    total_tokens,
                    total_cost_usd,
                    duration_ms,
                    json.dumps(trace_data)
                )
            )
            await db.commit()

    async def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a completed execution trace record by ID.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM trace_records WHERE trace_id = ?", (trace_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                record = dict(row)
                record["trace_data"] = json.loads(record["trace_data"])
                return record

    async def log_token_usage(
        self,
        agent_id: str,
        step_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        step_cost_usd: Optional[float] = None,
        cost_usd: Optional[float] = None
    ) -> None:
        """
        Logs individual step token usage and calculated cost to token_ledger.
        """
        effective_cost = step_cost_usd if step_cost_usd is not None else (cost_usd if cost_usd is not None else 0.0)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO token_ledger (
                    agent_id, step_id, model, prompt_tokens, completion_tokens, step_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_id,
                    step_id,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    effective_cost
                )
            )
            await db.commit()

    async def get_agent_total_cost(self, agent_id: str) -> float:
        """
        Calculates cumulative token spend cost for a given agent from token_ledger.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT SUM(step_cost_usd) FROM token_ledger WHERE agent_id = ?", (agent_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return result[0] if result and result[0] is not None else 0.0

    async def get_global_telemetry_summary(self) -> Dict[str, Any]:
        """
        Calculates platform-wide cumulative token usage, total spend, and total agent executions from SQLite.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0), COALESCE(SUM(step_cost_usd), 0.0) FROM token_ledger"
            ) as cursor:
                row = await cursor.fetchone()
                ledger_tokens = row[0] if row else 0
                ledger_cost = row[1] if row else 0.0

            async with db.execute(
                "SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(total_cost_usd), 0.0), COUNT(DISTINCT agent_id) FROM trace_records"
            ) as cursor:
                row = await cursor.fetchone()
                trace_tokens = row[0] if row else 0
                trace_cost = row[1] if row else 0.0
                total_agents = row[2] if row else 0

            async with db.execute(
                "SELECT COUNT(DISTINCT agent_id) FROM token_ledger"
            ) as cursor:
                row = await cursor.fetchone()
                ledger_agents = row[0] if row else 0

            # Use maximums between token_ledger and trace_records to ensure no tokens/spend are missed
            final_tokens = max(int(ledger_tokens), int(trace_tokens))
            final_cost = max(float(ledger_cost), float(trace_cost))
            final_agents = max(int(ledger_agents), int(total_agents))

            return {
                "total_tokens": final_tokens,
                "total_cost_usd": final_cost,
                "total_agents": final_agents
            }

    async def clear_telemetry_history(self) -> None:
        """
        Purges historical trace records and token ledger entries from SQLite.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM token_ledger")
            await db.execute("DELETE FROM trace_records")
            await db.commit()

