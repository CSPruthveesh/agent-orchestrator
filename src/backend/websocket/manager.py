import json
import asyncio
import logging
from typing import Dict, Set, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """
    Thread-safe WebSocket Connection Manager for broadcasting real-time trace events,
    agent step execution transitions, and spend metrics to client browsers.
    """

    def __init__(self):
        # Active connections per agent_id: Dict[agent_id, Set[WebSocket]]
        self.agent_subscriptions: Dict[str, Set[WebSocket]] = {}
        # Global active dashboard connections (not subscribed to a specific agent_id)
        self.global_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, agent_id: Optional[str] = None) -> None:
        """
        Accepts WebSocket connection and subscribes to agent_id topic or global dashboard stream.
        """
        await websocket.accept()
        async with self._lock:
            if agent_id:
                if agent_id not in self.agent_subscriptions:
                    self.agent_subscriptions[agent_id] = set()
                self.agent_subscriptions[agent_id].add(websocket)
                logger.info(f"WebSocket client subscribed to agent '{agent_id}' trace channel")
            else:
                self.global_connections.add(websocket)
                logger.info("WebSocket client subscribed to global dashboard stream")

    async def disconnect(self, websocket: WebSocket, agent_id: Optional[str] = None) -> None:
        """
        Removes WebSocket connection cleanly from active subscription sets.
        """
        async with self._lock:
            self.global_connections.discard(websocket)
            if agent_id and agent_id in self.agent_subscriptions:
                self.agent_subscriptions[agent_id].discard(websocket)
                if not self.agent_subscriptions[agent_id]:
                    del self.agent_subscriptions[agent_id]
                logger.info(f"WebSocket client unsubscribed from agent '{agent_id}'")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """
        Sends a single JSON payload to a specific WebSocket client.
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Error sending WebSocket message: {e}")

    async def broadcast_to_agent(self, agent_id: str, event: Dict[str, Any]) -> int:
        """
        Broadcasting structured JSON step execution event to all WebSocket clients subscribed to agent_id.
        Returns number of clients reached.
        """
        async with self._lock:
            target_sockets = set(self.agent_subscriptions.get(agent_id, set()))

        if not target_sockets:
            return 0

        stale_sockets = set()
        sent_count = 0

        for ws in target_sockets:
            try:
                await ws.send_json(event)
                sent_count += 1
            except Exception as e:
                logger.warning(f"WebSocket send failed for agent '{agent_id}': {e}")
                stale_sockets.add(ws)

        if stale_sockets:
            async with self._lock:
                for ws in stale_sockets:
                    if agent_id in self.agent_subscriptions:
                        self.agent_subscriptions[agent_id].discard(ws)

        return sent_count

    async def broadcast_global(self, event: Dict[str, Any]) -> int:
        """
        Broadcasts an event payload to global dashboard client web sockets.
        """
        async with self._lock:
            target_sockets = set(self.global_connections)

        if not target_sockets:
            return 0

        stale_sockets = set()
        sent_count = 0

        for ws in target_sockets:
            try:
                await ws.send_json(event)
                sent_count += 1
            except Exception as e:
                stale_sockets.add(ws)

        if stale_sockets:
            async with self._lock:
                for ws in stale_sockets:
                    self.global_connections.discard(ws)

        return sent_count

    def get_subscription_count(self, agent_id: Optional[str] = None) -> int:
        """
        Returns count of active web sockets for an agent or total active connections across all channels.
        """
        if agent_id:
            return len(self.agent_subscriptions.get(agent_id, set()))
        total_agent_sockets = sum(len(s) for s in self.agent_subscriptions.values())
        return len(self.global_connections) + total_agent_sockets


# Global singleton connection manager
ws_manager = WebSocketConnectionManager()
