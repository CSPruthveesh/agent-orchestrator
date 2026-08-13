import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class StepNodeType(str, Enum):
    SUPERVISOR_PROMPT = "SUPERVISOR_PROMPT"
    WORKER_PROMPT = "WORKER_PROMPT"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    STATE_TRANSITION = "STATE_TRANSITION"


class AgentConfig(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_agent_id: Optional[str] = None
    goal: str
    model: str = "gemini-2.5-flash"
    max_budget_usd: float = 1.00
    available_tools: List[str] = Field(default_factory=list)
    simulate_delay_sec: float = 0.0


class ExecutionStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_step_id: Optional[str] = None
    agent_id: str
    node_type: StepNodeType
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    step_cost_usd: float = 0.0
    duration_ms: int = 0
    created_at: float = Field(default_factory=time.time)


class AgentState(BaseModel):
    agent_id: str
    parent_agent_id: Optional[str] = None
    status: AgentStatus = AgentStatus.IDLE
    current_step_index: int = 0
    history: List[ExecutionStep] = Field(default_factory=list)
    accumulated_tokens: int = 0
    accumulated_cost_usd: float = 0.0
    context_data: Dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=time.time)


class ToolCallRequest(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    params: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 5000
    max_retries: int = 3


class ToolCallResult(BaseModel):
    call_id: Optional[str] = None
    tool_name: str
    status: str  # SUCCESS, FAILED, TIMEOUT
    output: Any = None
    execution_time_ms: int = 0
    error: Optional[str] = None
