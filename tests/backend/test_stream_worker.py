import pytest
import redis.asyncio as aioredis
from src.backend.engine.models import ToolCallRequest
from src.backend.queues.stream_worker import (
    ToolStreamProducer,
    ToolStreamWorker,
    STREAM_TOOL_CALLS,
    CONSUMER_GROUP_TOOL_WORKERS
)


@pytest.mark.asyncio
async def test_stream_producer_and_consumer():
    """
    Tests publishing tool requests to Redis Stream and consuming them via ToolStreamWorker.
    """
    try:
        client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable for stream worker test: {e}")

    producer = ToolStreamProducer(redis_client=client)
    worker = ToolStreamWorker(redis_client=client, consumer_group="test_group_workers", stream_name="test_stream_calls")

    agent_id = "agent-stream-test-001"
    step_id = "step-001"
    req = ToolCallRequest(
        tool_name="cpp_sandbox",
        params={"code": "int main() { return 0; }"},
        timeout_ms=3000
    )

    processed_payloads = []

    async def sample_handler(payload):
        processed_payloads.append(payload)

    try:
        # Publish message to stream
        msg_id = await producer.publish_tool_call(agent_id, step_id, req)
        assert msg_id is not None

        # Consume message via worker
        count = await worker.consume_messages(
            consumer_name="worker-1",
            handler_func=sample_handler,
            block_ms=500
        )

        assert count >= 1
        assert len(processed_payloads) >= 1

        payload = processed_payloads[0]
        assert payload["agent_id"] == agent_id
        assert payload["step_id"] == step_id
        assert payload["tool_name"] == "cpp_sandbox"
        assert payload["params"] == {"code": "int main() { return 0; }"}
        assert payload["timeout_ms"] == 3000

    finally:
        await client.delete("test_stream_calls")
        await client.aclose()
