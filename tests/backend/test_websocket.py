import pytest
from unittest.mock import AsyncMock
from src.backend.websocket.manager import WebSocketConnectionManager


@pytest.mark.asyncio
async def test_websocket_manager_lifecycle():
    """
    Tests WebSocket client connection registration, messaging, agent broadcasting, and disconnection.
    """
    manager = WebSocketConnectionManager()
    agent_id = "agent-ws-test-001"

    # Create mock WebSocket for agent channel
    mock_agent_ws = AsyncMock()
    mock_agent_ws.accept = AsyncMock()
    mock_agent_ws.send_json = AsyncMock()

    # Create mock WebSocket for global channel
    mock_global_ws = AsyncMock()
    mock_global_ws.accept = AsyncMock()
    mock_global_ws.send_json = AsyncMock()

    # 1. Connect agent WS client
    await manager.connect(mock_agent_ws, agent_id)
    assert manager.get_subscription_count(agent_id) == 1

    # 2. Connect global WS client
    await manager.connect(mock_global_ws, agent_id=None)
    assert manager.get_subscription_count() == 2

    # 3. Broadcast event to agent
    event_payload = {
        "event_type": "STEP_EXECUTION_STARTED",
        "agent_id": agent_id,
        "step_id": "step-100"
    }
    sent_count = await manager.broadcast_to_agent(agent_id, event_payload)
    assert sent_count == 1
    mock_agent_ws.send_json.assert_called_with(event_payload)

    # 4. Broadcast global event
    global_event = {"event_type": "SYSTEM_METRIC_UPDATE", "active_workers": 4}
    global_sent = await manager.broadcast_global(global_event)
    assert global_sent == 1
    mock_global_ws.send_json.assert_called_with(global_event)

    # 5. Disconnect WS clients cleanly
    await manager.disconnect(mock_agent_ws, agent_id)
    await manager.disconnect(mock_global_ws, agent_id=None)
    assert manager.get_subscription_count(agent_id) == 0
    assert manager.get_subscription_count() == 0


@pytest.mark.asyncio
async def test_websocket_stale_socket_cleanup():
    """
    Asserts that send exceptions automatically purge broken/disconnected sockets.
    """
    manager = WebSocketConnectionManager()
    agent_id = "agent-broken-ws"

    mock_broken_ws = AsyncMock()
    mock_broken_ws.accept = AsyncMock()
    mock_broken_ws.send_json = AsyncMock(side_effect=RuntimeError("Connection closed"))

    await manager.connect(mock_broken_ws, agent_id)
    assert manager.get_subscription_count(agent_id) == 1

    # Trigger broadcast -> Should handle exception and purge broken socket
    sent = await manager.broadcast_to_agent(agent_id, {"event": "TEST"})
    assert sent == 0
    assert manager.get_subscription_count(agent_id) == 0
