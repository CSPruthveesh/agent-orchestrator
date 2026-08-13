import pytest
import redis.asyncio as aioredis
from src.backend.queues.dlq_handler import DeadLetterQueueHandler


@pytest.mark.asyncio
async def test_dlq_publish_list_and_replay():
    """
    Tests publishing failed tool execution to DLQ, listing DLQ entries, and replaying to target stream.
    """
    try:
        client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable for DLQ test: {e}")

    dlq_stream = "test_stream_dlq"
    target_stream = "test_stream_target"
    handler = DeadLetterQueueHandler(redis_client=client, dlq_stream_name=dlq_stream)

    agent_id = "agent-dlq-test-001"
    step_id = "step-dlq-001"

    try:
        # 1. Publish failure to DLQ
        dlq_msg_id = await handler.publish_to_dlq(
            agent_id=agent_id,
            step_id=step_id,
            tool_name="http_tool",
            error_message="HTTP 500 Server Error after 3 retries",
            raw_payload={"url": "https://api.example.com/fail", "params": {"method": "GET"}}
        )
        assert dlq_msg_id is not None

        # 2. Assert count and list entries
        count = await handler.get_dlq_count()
        assert count == 1

        entries = await handler.get_dlq_entries()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["agent_id"] == agent_id
        assert entry["tool_name"] == "http_tool"
        assert "HTTP 500" in entry["error_message"]

        # 3. Replay DLQ entry back to target stream
        replayed_id = await handler.replay_dlq_entry(
            dlq_message_id=dlq_msg_id,
            target_stream=target_stream
        )
        assert replayed_id is not None

        # 4. Verify DLQ stream is now empty and target stream contains replayed item
        remaining_count = await handler.get_dlq_count()
        assert remaining_count == 0

        target_items = await client.xrange(target_stream)
        assert len(target_items) == 1
        assert target_items[0][1]["is_replayed"] == "true"
        assert target_items[0][1]["agent_id"] == agent_id

    finally:
        await client.delete(dlq_stream, target_stream)
        await client.aclose()
