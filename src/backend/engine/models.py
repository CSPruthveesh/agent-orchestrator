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
    LLM_REASONING = "LLM_REASONING"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    FAN_OUT_DISPATCH = "FAN_OUT_DISPATCH"
    STATE_CHECKPOINT = "STATE_CHECKPOINT"


class ToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Target tool name to invoke")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to tool")
    timeout_ms: int = Field(default=5000, description="Execution deadline in milliseconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts on failure")


class ToolCallResult(BaseModel):
    tool_name: str
    status: str  # "SUCCESS" | "FAILED" | "TIMEOUT"
    output: Any
    execution_time_ms: int
    error: Optional[str] = None


class ExecutionStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_step_id: Optional[str] = None
    agent_id: str
    node_type: StepNodeType
    input_payload: Dict[str, Any] = Field(default_factory=dict)
    output_payload: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    step_cost_usd: float = 0.0
    duration_ms: int = 0
    timestamp: float = Field(default_factory=time.time)


class AgentConfig(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_agent_id: Optional[str] = None
    goal: str = Field(..., description="High-level goal description for the agent")
    available_tools: List[str] = Field(default_factory=lambda: ["http_tool", "cpp_sandbox"])
    model: str = Field(default="gemini-2.5-flash", description="Target LLM model")
    max_budget_usd: float = Field(default=1.00, description="Max dollar limit for tokens")
    max_workers: int = Field(default=3, description="Max sub-agent workers for fan-out")


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
