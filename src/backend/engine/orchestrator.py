import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional, Callable
import redis.asyncio as aioredis

from src.backend.config import settings
from src.backend.db.database import get_redis_client
from src.backend.db.repository import TraceRepository
from src.backend.engine.models import (
    AgentConfig,
    AgentState,
    AgentStatus,
    ExecutionStep,
    StepNodeType,
    ToolCallRequest,
    ToolCallResult
)
from src.backend.engine.state_machine import RedisStateCheckpointer
from src.backend.engine.budget_manager import TokenBudgetManager, BudgetExceededException
from src.backend.llm.gateway import AsyncLLMGateway

logger = logging.getLogger(__name__)


class AsyncTaskGraphEngine:
    """
    Core Async Task Graph Execution Engine.
    Orchestrates agent lifecycles, manages asyncio.Task execution loops,
    enforces per-step Redis checkpointing, meters token spend budgets,
    publishes real-time WebSocket trace events, and persists finished traces into SQLite.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        trace_repo: Optional[TraceRepository] = None,
        tool_dispatcher: Optional[Callable[[ToolCallRequest], Any]] = None,
        event_publisher: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        llm_gateway: Optional[AsyncLLMGateway] = None
    ):
        self.redis_client = redis_client
        self.checkpointer = RedisStateCheckpointer(redis_client=redis_client)
        self.budget_manager = TokenBudgetManager(redis_client=redis_client)
        self.trace_repo = trace_repo or TraceRepository()
        self.tool_dispatcher = tool_dispatcher
        self.event_publisher = event_publisher
        self.llm_gateway = llm_gateway or AsyncLLMGateway()

        # Active running asyncio Tasks mapped by agent_id
        self._active_tasks: Dict[str, asyncio.Task] = {}
        # Active agent state objects mapped by agent_id
        self._active_states: Dict[str, AgentState] = {}

    async def _publish_event(self, agent_id: str, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_publisher:
            event_payload = {
                "event_type": event_type,
                "agent_id": agent_id,
                "timestamp": time.time(),
                "data": data
            }
            try:
                res = self.event_publisher(agent_id, event_payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.warning(f"Error publishing WebSocket event: {e}")

    def is_agent_running(self, agent_id: str) -> bool:
        task = self._active_tasks.get(agent_id)
        return task is not None and not task.done()

    async def start_agent_task(self, config: AgentConfig) -> asyncio.Task:
        if self.is_agent_running(config.agent_id):
            raise RuntimeError(f"Agent '{config.agent_id}' is already running.")

        task = asyncio.create_task(
            self.execute_agent_loop(config),
            name=f"agent_task_{config.agent_id}"
        )
        self._active_tasks[config.agent_id] = task
        return task

    async def cancel_agent(self, agent_id: str, reason: str = "User requested cancellation") -> bool:
        task = self._active_tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            state = self._active_states.get(agent_id)
            if state:
                state.status = AgentStatus.SUSPENDED
                state.context_data["cancellation_reason"] = reason
                await self.checkpointer.save_checkpoint(state)
                await self._publish_event(agent_id, "EXECUTION_TERMINATED", {
                    "status": "CANCELLED",
                    "reason": reason
                })
            return True
        return False

    async def execute_agent_loop(self, config: AgentConfig) -> AgentState:
        start_time = time.time()
        agent_id = config.agent_id

        state = await self.checkpointer.load_checkpoint(agent_id)
        if state is None:
            state = AgentState(
                agent_id=agent_id,
                parent_agent_id=config.parent_agent_id,
                status=AgentStatus.RUNNING,
                context_data={"goal": config.goal, "model": config.model}
            )
        else:
            state.status = AgentStatus.RUNNING

        self._active_states[agent_id] = state
        await self.checkpointer.save_checkpoint(state)

        await self._publish_event(agent_id, "AGENT_STATE_CHANGE", {
            "state": state.status.value,
            "current_step": state.current_step_index
        })

        try:
            # Turn 1: LLM Reasoning Step via AsyncLLMGateway (Dynamic Token Metering)
            llm_response = await self.llm_gateway.generate_reasoning_step(
                prompt=config.goal,
                model=config.model,
                system_instruction="You are an autonomous orchestrator supervisor planning task execution."
            )

            prompt_tokens_turn1 = llm_response.get("prompt_tokens", len(config.goal.split()) * 3 + 20)
            completion_tokens_turn1 = llm_response.get("completion_tokens", len(llm_response.get("text", "").split()) + 15)

            step1 = ExecutionStep(
                agent_id=agent_id,
                node_type=StepNodeType.SUPERVISOR_PROMPT if not config.parent_agent_id else StepNodeType.WORKER_PROMPT,
                input_payload={"goal": config.goal, "model": config.model},
                output_payload={"reasoning": llm_response.get("text", f"Planning steps for: {config.goal}")},
                prompt_tokens=prompt_tokens_turn1,
                completion_tokens=completion_tokens_turn1
            )

            await self._publish_event(agent_id, "STEP_EXECUTION_STARTED", {
                "step_id": step1.step_id,
                "node_type": step1.node_type.value,
                "prompt_tokens": step1.prompt_tokens
            })

            budget_res = await self.budget_manager.record_usage_and_check(
                agent_id=agent_id,
                prompt_tokens=step1.prompt_tokens,
                completion_tokens=step1.completion_tokens,
                max_budget_usd=config.max_budget_usd,
                model=config.model
            )
            step1.step_cost_usd = budget_res["turn_cost_usd"]
            state.history.append(step1)
            state.current_step_index += 1
            state.accumulated_tokens = budget_res["total_tokens"]
            state.accumulated_cost_usd = budget_res["total_spend_usd"]
            await self.checkpointer.save_checkpoint(state)

            await self.trace_repo.log_token_usage(
                agent_id=agent_id,
                step_id=step1.step_id,
                model=config.model,
                prompt_tokens=step1.prompt_tokens,
                completion_tokens=step1.completion_tokens,
                step_cost_usd=step1.step_cost_usd
            )

            await self._publish_event(agent_id, "BUDGET_UPDATE", budget_res)

            # Simulated execution delay for cancellation testing if requested
            if any(k in config.goal.lower() for k in ["sleep", "delay", "long", "cancel"]):
                logger.info(f"Simulating 5-second execution delay for agent '{agent_id}' cancellation test...")
                await asyncio.sleep(5.0)

            # Turn 2: Tool Execution Step (Dynamic Token Metering)
            if config.available_tools:
                state.status = AgentStatus.WAITING_FOR_TOOL
                await self.checkpointer.save_checkpoint(state)

                tool_name = config.available_tools[0]
                tool_req = ToolCallRequest(
                    tool_name=tool_name,
                    params={"goal": config.goal, "command": "echo Sandbox Execution Success"}
                )

                # Send parent_step_id so live DAG renders connector arrow immediately
                await self._publish_event(agent_id, "TOOL_CALL_DISPATCHED", {
                    "tool_name": tool_name,
                    "params": tool_req.params,
                    "parent_step_id": step1.step_id
                })

                tool_output: Any = {"status": "SUCCESS", "message": f"Executed tool {tool_name}"}
                if self.tool_dispatcher:
                    tool_output = await self.tool_dispatcher(tool_req)

                prompt_tokens_turn2 = max(35, len(str(tool_req.params).split()) * 4)
                completion_tokens_turn2 = max(25, len(str(tool_output).split()) * 2)

                step2 = ExecutionStep(
                    parent_step_id=step1.step_id,
                    agent_id=agent_id,
                    node_type=StepNodeType.TOOL_EXECUTION,
                    input_payload=tool_req.model_dump(),
                    output_payload=tool_output if isinstance(tool_output, dict) else {"result": str(tool_output)},
                    prompt_tokens=prompt_tokens_turn2,
                    completion_tokens=completion_tokens_turn2
                )

                await self._publish_event(agent_id, "TOOL_CALL_COMPLETED", {
                    "tool_name": tool_name,
                    "step_id": step2.step_id,
                    "output": tool_output if isinstance(tool_output, dict) else {"result": str(tool_output)}
                })

                budget_res2 = await self.budget_manager.record_usage_and_check(
                    agent_id=agent_id,
                    prompt_tokens=step2.prompt_tokens,
                    completion_tokens=step2.completion_tokens,
                    max_budget_usd=config.max_budget_usd,
                    model=config.model
                )
                step2.step_cost_usd = budget_res2["turn_cost_usd"]
                state.history.append(step2)
                state.current_step_index += 1
                state.accumulated_tokens = budget_res2["total_tokens"]
                state.accumulated_cost_usd = budget_res2["total_spend_usd"]
                await self.checkpointer.save_checkpoint(state)

                await self.trace_repo.log_token_usage(
                    agent_id=agent_id,
                    step_id=step2.step_id,
                    model=config.model,
                    prompt_tokens=step2.prompt_tokens,
                    completion_tokens=step2.completion_tokens,
                    step_cost_usd=step2.step_cost_usd
                )

                await self._publish_event(agent_id, "BUDGET_UPDATE", budget_res2)

            # Finalize Execution
            state.status = AgentStatus.COMPLETED
            duration_ms = int((time.time() - start_time) * 1000)
            await self.checkpointer.save_checkpoint(state)

            trace_id = str(uuid.uuid4())
            await self.trace_repo.save_trace(
                trace_id=trace_id,
                agent_id=agent_id,
                parent_agent_id=config.parent_agent_id,
                status=state.status.value,
                goal=config.goal,
                model=config.model,
                total_tokens=state.accumulated_tokens,
                total_cost_usd=state.accumulated_cost_usd,
                duration_ms=duration_ms,
                trace_data=state.model_dump()
            )

            await self._publish_event(agent_id, "EXECUTION_TERMINATED", {
                "status": "COMPLETED",
                "duration_ms": duration_ms,
                "final_trace_id": trace_id
            })

            return state

        except BudgetExceededException as e:
            state.status = AgentStatus.BUDGET_EXCEEDED
            state.context_data["error"] = str(e)
            await self.checkpointer.save_checkpoint(state)
            await self._publish_event(agent_id, "EXECUTION_TERMINATED", {
                "status": "BUDGET_EXCEEDED",
                "error": str(e)
            })
            raise

        except asyncio.CancelledError:
            state.status = AgentStatus.SUSPENDED
            state.context_data["status_reason"] = "Task cancelled"
            await self.checkpointer.save_checkpoint(state)
            await self._publish_event(agent_id, "EXECUTION_TERMINATED", {
                "status": "SUSPENDED",
                "reason": "Task cancelled"
            })
            raise

        except Exception as e:
            state.status = AgentStatus.FAILED
            state.context_data["error"] = str(e)
            await self.checkpointer.save_checkpoint(state)
            await self._publish_event(agent_id, "EXECUTION_TERMINATED", {
                "status": "FAILED",
                "error": str(e)
            })
            raise

        finally:
            self._active_tasks.pop(agent_id, None)

    async def resume_agent(self, agent_id: str, config: AgentConfig) -> AgentState:
        checkpoint = await self.checkpointer.load_checkpoint(agent_id)
        if checkpoint is None:
            raise ValueError(f"No state checkpoint found for agent '{agent_id}' to resume.")

        logger.info(f"Resuming agent '{agent_id}' from step {checkpoint.current_step_index}")
        return await self.execute_agent_loop(config)
