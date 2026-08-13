import json
import redis.asyncio as aioredis
from typing import Optional, List, Dict, Any
from src.backend.db.database import get_redis_client
from src.backend.engine.models import AgentState, AgentStatus


class RedisStateCheckpointer:
    """
    Per-step state checkpointer serializing agent state machines into Redis Hashes
    at key `agent:{agent_id}:state` for sub-2 second crash recovery.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        ttl_seconds: int = 86400  # 24-hour state checkpoint retention
    ):
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    @staticmethod
    def _make_key(agent_id: str) -> str:
        return f"agent:{agent_id}:state"

    async def save_checkpoint(self, state: AgentState) -> None:
        """
        Serializes AgentState into a Redis Hash and sets expiration TTL.
        """
        client = await self._get_client()
        key = self._make_key(state.agent_id)

        # Dump Pydantic state model into JSON dictionary fields
        mapping = {
            "agent_id": state.agent_id,
            "parent_agent_id": state.parent_agent_id or "",
            "status": state.status.value,
            "current_step_index": str(state.current_step_index),
            "accumulated_tokens": str(state.accumulated_tokens),
            "accumulated_cost_usd": str(state.accumulated_cost_usd),
            "history": json.dumps([step.model_dump() for step in state.history]),
            "context_data": json.dumps(state.context_data),
            "updated_at": str(state.updated_at)
        }

        async with client.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=mapping)
            if self.ttl_seconds > 0:
                pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def load_checkpoint(self, agent_id: str) -> Optional[AgentState]:
        """
        Loads and deserializes an AgentState from its Redis Hash checkpoint key.
        Returns None if checkpoint does not exist.
        """
        client = await self._get_client()
        key = self._make_key(agent_id)
        raw_hash: Dict[str, str] = await client.hgetall(key)

        if not raw_hash:
            return None

        # Reconstruct Pydantic AgentState instance
        history_raw = json.loads(raw_hash.get("history", "[]"))
        context_raw = json.loads(raw_hash.get("context_data", "{}"))

        return AgentState(
            agent_id=raw_hash["agent_id"],
            parent_agent_id=raw_hash.get("parent_agent_id") or None,
            status=AgentStatus(raw_hash.get("status", "IDLE")),
            current_step_index=int(raw_hash.get("current_step_index", 0)),
            history=history_raw,
            accumulated_tokens=int(raw_hash.get("accumulated_tokens", 0)),
            accumulated_cost_usd=float(raw_hash.get("accumulated_cost_usd", 0.0)),
            context_data=context_raw,
            updated_at=float(raw_hash.get("updated_at", 0.0))
        )

    async def delete_checkpoint(self, agent_id: str) -> bool:
        """
        Deletes checkpoint key for completed or terminated agent.
        """
        client = await self._get_client()
        key = self._make_key(agent_id)
        res = await client.delete(key)
        return res > 0

    async def list_active_agent_ids(self) -> List[str]:
        """
        Scans all active agent checkpoint keys matching `agent:*:state`.
        """
        client = await self._get_client()
        keys = []
        async for key in client.scan_iter(match="agent:*:state"):
            # Extract agent_id from `agent:{id}:state`
            parts = key.split(":")
            if len(parts) >= 3:
                keys.append(parts[1])
        return keys
