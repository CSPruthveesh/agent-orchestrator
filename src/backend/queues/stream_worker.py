import json
import asyncio
import logging
import redis.asyncio as aioredis
from typing import Optional, Dict, Any, Callable
from src.backend.db.database import get_redis_client
from src.backend.engine.models import ToolCallRequest

logger = logging.getLogger(__name__)

STREAM_TOOL_CALLS = "stream:tool_calls"
CONSUMER_GROUP_TOOL_WORKERS = "group:tool_workers"


class ToolStreamProducer:
    """
    Publishes tool call invocation requests to Redis Stream `stream:tool_calls`.
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis_client = redis_client

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    async def publish_tool_call(
        self,
        agent_id: str,
        step_id: str,
        request: ToolCallRequest
    ) -> str:
        """
        Publishes a tool execution payload as a Redis Stream entry.
        Returns the generated Redis Stream entry ID (e.g. '1770854400000-0').
        """
        client = await self._get_client()
        entry_payload = {
            "agent_id": agent_id,
            "step_id": step_id,
            "tool_name": request.tool_name,
            "params": json.dumps(request.params),
            "timeout_ms": str(request.timeout_ms),
            "max_retries": str(request.max_retries),
            "timestamp": str(asyncio.get_event_loop().time())
        }

        message_id = await client.xadd(
            name=STREAM_TOOL_CALLS,
            fields=entry_payload
        )
        logger.info(f"Published tool request '{request.tool_name}' for agent '{agent_id}' -> Message ID: {message_id}")
        return message_id


class ToolStreamWorker:
    """
    Consumer group worker reading tool execution requests from Redis Stream `stream:tool_calls`,
    dispatching execution, and acknowledging (`xack`) completed items.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        consumer_group: str = CONSUMER_GROUP_TOOL_WORKERS,
        stream_name: str = STREAM_TOOL_CALLS
    ):
        self.redis_client = redis_client
        self.consumer_group = consumer_group
        self.stream_name = stream_name
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    async def ensure_consumer_group(self) -> None:
        """
        Creates consumer group on the Redis stream if it doesn't already exist.
        """
        client = await self._get_client()
        try:
            await client.xgroup_create(
                name=self.stream_name,
                groupname=self.consumer_group,
                id="0",
                mkstream=True
            )
            logger.info(f"Created consumer group '{self.consumer_group}' on stream '{self.stream_name}'")
        except aioredis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass  # Group already exists
            else:
                raise

    async def consume_messages(
        self,
        consumer_name: str,
        handler_func: Callable[[Dict[str, Any]], Any],
        batch_count: int = 5,
        block_ms: int = 1000
    ) -> int:
        """
        Reads a batch of pending/new stream entries, calls handler, and acknowledges (XACK).
        Returns count of processed messages in batch.
        """
        client = await self._get_client()
        await self.ensure_consumer_group()

        entries = await client.xreadgroup(
            groupname=self.consumer_group,
            consumername=consumer_name,
            streams={self.stream_name: ">"},
            count=batch_count,
            block=block_ms
        )

        if not entries:
            return 0

        processed_count = 0
        for stream_key, message_list in entries:
            for message_id, raw_fields in message_list:
                try:
                    payload = {
                        "message_id": message_id,
                        "agent_id": raw_fields.get("agent_id"),
                        "step_id": raw_fields.get("step_id"),
                        "tool_name": raw_fields.get("tool_name"),
                        "params": json.loads(raw_fields.get("params", "{}")),
                        "timeout_ms": int(raw_fields.get("timeout_ms", 5000)),
                        "max_retries": int(raw_fields.get("max_retries", 3))
                    }

                    # Execute handler callback
                    if asyncio.iscoroutinefunction(handler_func):
                        await handler_func(payload)
                    else:
                        handler_func(payload)

                    # Acknowledge processed item in stream consumer group
                    await client.xack(self.stream_name, self.consumer_group, message_id)
                    processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing stream message {message_id}: {e}")

        return processed_count

    async def start_worker_loop(
        self,
        consumer_name: str,
        handler_func: Callable[[Dict[str, Any]], Any]
    ) -> None:
        """
        Starts persistent background loop reading and processing stream messages.
        """
        self._running = True
        logger.info(f"Worker '{consumer_name}' started listening on stream '{self.stream_name}'")
        while self._running:
            try:
                await self.consume_messages(consumer_name, handler_func)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

    def stop() -> None:
        """
        Signals worker loop to stop.
        """
        self._running = False
