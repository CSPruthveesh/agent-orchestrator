import json
import asyncio
import logging
import redis.asyncio as aioredis
from typing import List, Dict, Any, Optional
from src.backend.config import settings
from src.backend.db.database import get_redis_client
from src.backend.engine.models import AgentConfig, AgentState, AgentStatus
from src.backend.engine.orchestrator import AsyncTaskGraphEngine

logger = logging.getLogger(__name__)

COORDINATION_CHANNEL = "channel:agent:coordination"


class MultiAgentFanOutManager:
    """
    Supervisor-to-worker fan-out pattern manager enabling supervisor agents to spawn
    parallel worker sub-tasks, coordinate via Redis Pub/Sub channels, and aggregate
    results concurrently with `asyncio.gather()`.
    """

    def __init__(
        self,
        orchestrator: AsyncTaskGraphEngine,
        redis_client: Optional[aioredis.Redis] = None,
        coordination_channel: str = COORDINATION_CHANNEL
    ):
        self.orchestrator = orchestrator
        self.redis_client = redis_client
        self.coordination_channel = coordination_channel

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    async def publish_coordination_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Publishes a coordination event to Redis Pub/Sub.
        """
        client = await self._get_client()
        event = {
            "event_type": event_type,
            "timestamp": asyncio.get_event_loop().time(),
            "payload": payload
        }
        await client.publish(self.coordination_channel, json.dumps(event))

    async def fan_out_subtasks(
        self,
        supervisor_id: str,
        subtask_configs: List[AgentConfig]
    ) -> List[AgentState]:
        """
        Spawns parallel worker sub-agent coroutines for a supervisor agent,
        coordinates execution over Redis Pub/Sub, and aggregates results via `asyncio.gather()`.
        """
        if not subtask_configs:
            return []

        if len(subtask_configs) > settings.MAX_WORKERS_PER_SUPERVISOR:
            raise ValueError(
                f"Subtask count {len(subtask_configs)} exceeds max workers limit "
                f"({settings.MAX_WORKERS_PER_SUPERVISOR})"
            )

        # Assign supervisor relationship & validate depth
        for config in subtask_configs:
            config.parent_agent_id = supervisor_id

        # Publish FAN_OUT_DISPATCH event
        await self.publish_coordination_event(
            event_type="FAN_OUT_DISPATCH",
            payload={
                "supervisor_id": supervisor_id,
                "worker_count": len(subtask_configs),
                "worker_ids": [c.agent_id for c in subtask_configs]
            }
        )

        logger.info(f"Supervisor '{supervisor_id}' fanning out {len(subtask_configs)} worker sub-tasks")

        # Create worker coroutines
        worker_coros = [
            self.orchestrator.execute_agent_loop(config)
            for config in subtask_configs
        ]

        # Execute parallel worker sub-agent tasks concurrently
        results = await asyncio.gather(*worker_coros, return_exceptions=True)

        aggregated_states: List[AgentState] = []
        for i, res in enumerate(results):
            worker_id = subtask_configs[i].agent_id
            if isinstance(res, Exception):
                logger.error(f"Worker '{worker_id}' failed during fan-out: {res}")
                failed_state = AgentState(
                    agent_id=worker_id,
                    parent_agent_id=supervisor_id,
                    status=AgentStatus.FAILED,
                    context_data={"error": str(res)}
                )
                aggregated_states.append(failed_state)
            else:
                aggregated_states.append(res)

        # Publish FAN_OUT_COMPLETED event
        await self.publish_coordination_event(
            event_type="FAN_OUT_COMPLETED",
            payload={
                "supervisor_id": supervisor_id,
                "completed_workers": len([s for s in aggregated_states if s.status == AgentStatus.COMPLETED]),
                "total_workers": len(subtask_configs)
            }
        )

        return aggregated_states
