import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from src.backend.main import app, engine
from src.backend.db.database import init_sqlite_db
from src.backend.engine.models import AgentConfig, AgentStatus


@pytest.fixture
def sync_client():
    return TestClient(app)


def test_health_check_endpoint(sync_client):
    """
    Asserts /health endpoint returns HTTP 200 and healthy status payload.
    """
    response = sync_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Async AI Agent" in data["project"]


def test_websocket_trace_connection(sync_client):
    """
    Asserts real-time WebSocket connection endpoint accepts subscriptions.
    """
    agent_id = "test-ws-client-001"
    with sync_client.websocket_connect(f"/ws/traces/{agent_id}") as websocket:
        data = websocket.receive_json()
        assert data["event_type"] == "WS_CONNECTED"
        assert data["agent_id"] == agent_id

        # Test PING/PONG
        websocket.send_json({"type": "PING"})
        pong = websocket.receive_json()
        assert pong["type"] == "PONG"


@pytest.mark.asyncio
async def test_agent_run_rest_endpoint():
    """
    Asserts POST /api/v1/agents/run triggers agent task and returns HTTP 202 Accepted.
    """
    try:
        r_client = aioredis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        await r_client.ping()
    except Exception as e:
        pytest.skip(f"Redis not reachable for REST API test: {e}")

    # Ensure SQLite tables exist
    await init_sqlite_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "goal": "Test REST API Trigger",
            "model": "gemini-2.5-flash",
            "max_budget_usd": 0.50,
            "available_tools": ["http_tool"]
        }

        response = await client.post("/api/v1/agents/run", json=payload)
        assert response.status_code == 202
        data = response.json()
        assert "agent_id" in data
        assert data["status"] == "RUNNING"
        assert "/ws/traces/" in data["websocket_url"]

        agent_id = data["agent_id"]
        
        # Wait for agent task loop to finish
        task = engine._active_tasks.get(agent_id)
        if task:
            await task

        status_resp = await client.get(f"/api/v1/agents/{agent_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "COMPLETED"

        await engine.checkpointer.delete_checkpoint(agent_id)
        await r_client.aclose()
