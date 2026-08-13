import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.backend.config import settings
from src.backend.db.database import init_sqlite_db, close_redis_pool
from src.backend.db.repository import TraceRepository
from src.backend.engine.models import AgentConfig, AgentState
from src.backend.engine.orchestrator import AsyncTaskGraphEngine
from src.backend.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Engine instance singleton with WebSocket event publisher hook
async def _ws_event_publisher(agent_id: str, event: Dict[str, Any]) -> None:
    """
    Relays orchestrator execution events to subscribed WebSocket client connections.
    """
    await ws_manager.broadcast_to_agent(agent_id, event)
    await ws_manager.broadcast_global(event)


engine = AsyncTaskGraphEngine(event_publisher=_ws_event_publisher)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager handling startup DB migrations & shutdown pool cleanup.
    """
    logger.info("Initializing SQLite database schemas...")
    await init_sqlite_db()
    yield
    logger.info("Closing Redis connection pool...")
    await close_redis_pool()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Configure CORS Middleware for Dashboard Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint returning platform status.
    """
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT
    }


@app.websocket("/ws/traces/{agent_id}")
async def websocket_agent_trace_endpoint(websocket: WebSocket, agent_id: str):
    """
    Real-time WebSocket endpoint streaming agent execution trace DAG events to browser dashboard.
    """
    await ws_manager.connect(websocket, agent_id)
    try:
        # Send initial connected greeting
        await ws_manager.send_personal_message(
            {
                "event_type": "WS_CONNECTED",
                "agent_id": agent_id,
                "message": f"Subscribed to real-time execution trace stream for agent '{agent_id}'"
            },
            websocket
        )

        while True:
            data = await websocket.receive_json()
            # Handle inbound client commands (e.g. ping, cancel)
            if data.get("type") == "PING":
                await ws_manager.send_personal_message({"type": "PONG"}, websocket)
            elif data.get("type") == "CANCEL_EXECUTION":
                await engine.cancel_agent(agent_id, reason="Cancelled via WebSocket")

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, agent_id)
    except Exception as e:
        logger.warning(f"WebSocket trace connection error for agent '{agent_id}': {e}")
        await ws_manager.disconnect(websocket, agent_id)


@app.post(
    f"{settings.API_V1_STR}/agents/run",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Agent Execution"]
)
async def run_agent(config: AgentConfig) -> Dict[str, Any]:
    """
    Submits a new agent task (goal, available tools, model, budget) and triggers execution.
    """
    try:
        task = await engine.start_agent_task(config)
        return {
            "agent_id": config.agent_id,
            "status": "RUNNING",
            "goal": config.goal,
            "websocket_url": f"/ws/traces/{config.agent_id}"
        }
    except Exception as e:
        logger.error(f"Failed to start agent task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get(
    f"{settings.API_V1_STR}/agents/{{agent_id}}/status",
    tags=["Agent Execution"]
)
async def get_agent_status(agent_id: str) -> Dict[str, Any]:
    """
    Fetches real-time execution status and checkpoint state for an agent.
    """
    checkpoint = await engine.checkpointer.load_checkpoint(agent_id)
    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' checkpoint not found."
        )

    is_running = engine.is_agent_running(agent_id)
    return {
        "agent_id": checkpoint.agent_id,
        "is_running": is_running,
        "status": checkpoint.status.value,
        "current_step_index": checkpoint.current_step_index,
        "accumulated_tokens": checkpoint.accumulated_tokens,
        "accumulated_cost_usd": checkpoint.accumulated_cost_usd,
        "context_data": checkpoint.context_data
    }


@app.post(
    f"{settings.API_V1_STR}/agents/{{agent_id}}/cancel",
    tags=["Agent Execution"]
)
async def cancel_agent_execution(agent_id: str) -> Dict[str, Any]:
    """
    Cancels an active running agent execution task.
    """
    cancelled = await engine.cancel_agent(agent_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent_id}' is not actively running."
        )

    return {
        "agent_id": agent_id,
        "status": "CANCELLED",
        "message": f"Successfully cancelled agent task '{agent_id}'."
    }


@app.get(
    f"{settings.API_V1_STR}/traces/{{trace_id}}",
    tags=["Trace Telemetry"]
)
async def get_trace_record(trace_id: str) -> Dict[str, Any]:
    """
    Retrieves a completed execution trace record from SQLite.
    """
    repo = TraceRepository()
    record = await repo.get_trace(trace_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace record '{trace_id}' not found."
        )
    return record
