import json
import asyncio
import logging
import redis.asyncio as aioredis
from typing import Optional, List, Dict, Any
from src.backend.db.database import get_redis_client
from src.backend.queues.stream_worker import STREAM_TOOL_CALLS

logger = logging.getLogger(__name__)

STREAM_DLQ = "stream:dlq"


class DeadLetterQueueHandler:
    """
    Manages dead-letter queue routing for failed tool executions after max retry exhaustion,
    enabling trace inspection and manual task replaying.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        dlq_stream_name: str = STREAM_DLQ
    ):
        self.redis_client = redis_client
        self.dlq_stream_name = dlq_stream_name

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    async def publish_to_dlq(
        self,
        agent_id: str,
        step_id: str,
        tool_name: str,
        error_message: str,
        raw_payload: Dict[str, Any]
    ) -> str:
        """
        Publishes an unrecoverable tool execution failure payload into the dead-letter stream.
        """
        client = await self._get_client()
        dlq_entry = {
            "agent_id": agent_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "error_message": error_message,
            "raw_payload": json.dumps(raw_payload),
            "failed_at": str(asyncio.get_event_loop().time())
        }

        msg_id = await client.xadd(self.dlq_stream_name, fields=dlq_entry)
        logger.error(f"Routed failed tool '{tool_name}' for agent '{agent_id}' to DLQ -> Message ID: {msg_id}")
        return msg_id

    async def get_dlq_entries(self, count: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches up to `count` entries from the dead-letter queue for inspection.
        """
        client = await self._get_client()
        raw_entries = await client.xrange(self.dlq_stream_name, min="-", max="+", count=count)

        entries = []
        for msg_id, fields in raw_entries:
            entries.append({
                "dlq_message_id": msg_id,
                "agent_id": fields.get("agent_id"),
                "step_id": fields.get("step_id"),
                "tool_name": fields.get("tool_name"),
                "error_message": fields.get("error_message"),
                "raw_payload": json.loads(fields.get("raw_payload", "{}")),
                "failed_at": fields.get("failed_at")
            })

        return entries

    async def replay_dlq_entry(
        self,
        dlq_message_id: str,
        target_stream: str = STREAM_TOOL_CALLS
    ) -> Optional[str]:
        """
        Re-enqueues a failed DLQ entry back to the target tool stream and deletes it from DLQ.
        Returns the new message ID in the target stream.
        """
        client = await self._get_client()
        raw_entries = await client.xrange(self.dlq_stream_name, min=dlq_message_id, max=dlq_message_id)

        if not raw_entries:
            logger.warning(f"DLQ message ID '{dlq_message_id}' not found.")
            return None

        _, fields = raw_entries[0]
        raw_payload = json.loads(fields.get("raw_payload", "{}"))

        # Re-publish to main tool stream
        new_msg_id = await client.xadd(
            target_stream,
            fields={
                "agent_id": fields.get("agent_id", ""),
                "step_id": fields.get("step_id", ""),
                "tool_name": fields.get("tool_name", ""),
                "params": json.dumps(raw_payload.get("params", {})),
                "timeout_ms": str(raw_payload.get("timeout_ms", 5000)),
                "max_retries": str(raw_payload.get("max_retries", 3)),
                "is_replayed": "true"
            }
        )

        # Delete from DLQ
        await client.xdel(self.dlq_stream_name, dlq_message_id)
        logger.info(f"Replayed DLQ entry '{dlq_message_id}' to stream '{target_stream}' -> New ID: {new_msg_id}")
        return new_msg_id

    async def get_dlq_count(self) -> int:
        """
        Returns total number of items currently in the DLQ stream.
        """
        client = await self._get_client()
        return await client.xlen(self.dlq_stream_name)
