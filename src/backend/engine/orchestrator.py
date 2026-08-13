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

logger = logging.getLogger(__name__)


class AsyncTaskGraphEngine:
    """
    Core Async Task Graph Execution Engine.
    Orchestrates agent lifecycles, manages asyncio.Task execution loops,
    enforces per-step Redis checkpointing, meters token spend budgets,
    and persists finished execution traces into SQLite.
    """

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        trace_repo: Optional[TraceRepository] = None,
        tool_dispatcher: Optional[Callable[[ToolCallRequest], Any]] = None
    ):
        self.redis_client = redis_client
        self.checkpointer = RedisStateCheckpointer(redis_client=redis_client)
        self.budget_manager = TokenBudgetManager(redis_client=redis_client)
        self.trace_repo = trace_repo or TraceRepository()
        self.tool_dispatcher = tool_dispatcher

        # Active running asyncio Tasks mapped by agent_id
        self._active_tasks: Dict[str, asyncio.Task] = {}
        # Active agent state objects mapped by agent_id
        self._active_states: Dict[str, AgentState] = {}

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    def is_agent_running(self, agent_id: str) -> bool:
        """
        Returns True if the agent task is actively running.
        """
        task = self._active_tasks.get(agent_id)
        return task is not None and not task.done()

    async def start_agent_task(self, config: AgentConfig) -> asyncio.Task:
        """
        Spawns and manages an async background asyncio.Task for the agent.
        """
        if self.is_agent_running(config.agent_id):
            raise RuntimeError(f"Agent '{config.agent_id}' is already running.")

        task = asyncio.create_task(
            self.execute_agent_loop(config),
            name=f"agent_task_{config.agent_id}"
        )
        self._active_tasks[config.agent_id] = task
        return task

    async def cancel_agent(self, agent_id: str, reason: str = "User requested cancellation") -> bool:
        """
        Cancels an actively running agent task and updates state in Redis.
        """
        task = self._active_tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            state = self._active_states.get(agent_id)
            if state:
                state.status = AgentStatus.SUSPENDED
                state.context_data["cancellation_reason"] = reason
                await self.checkpointer.save_checkpoint(state)
            return True
        return False

    async def execute_agent_loop(self, config: AgentConfig) -> AgentState:
        """
        Main execution loop for an agent turn-by-turn processing graph.
        """
        start_time = time.time()
        agent_id = config.agent_id

        # 1. Initialize or recover agent state
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

        try:
            # 2. Simulated / Modular Execution Turns
            # Turn 1: Initial LLM Reasoning Step
            step1 = ExecutionStep(
                agent_id=agent_id,
                node_type=StepNodeType.SUPERVISOR_PROMPT if not config.parent_agent_id else StepNodeType.WORKER_PROMPT,
                input_payload={"goal": config.goal},
                output_payload={"reasoning": f"Planning steps to achieve: {config.goal}"},
                prompt_tokens=150,
                completion_tokens=75
            )

            # Record turn budget usage
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

            # Turn 2: Tool Execution Step (if tools provided)
            if config.available_tools:
                state.status = AgentStatus.WAITING_FOR_TOOL
                await self.checkpointer.save_checkpoint(state)

                tool_name = config.available_tools[0]
                tool_req = ToolCallRequest(
                    tool_name=tool_name,
                    params={"goal": config.goal, "command": "echo Sandbox Execution Success"}
                )

                tool_output: Any = {"status": "SUCCESS", "message": f"Executed tool {tool_name}"}
                if self.tool_dispatcher:
                    tool_output = await self.tool_dispatcher(tool_req)

                step2 = ExecutionStep(
                    parent_step_id=step1.step_id,
                    agent_id=agent_id,
                    node_type=StepNodeType.TOOL_EXECUTION,
                    input_payload=tool_req.model_dump(),
                    output_payload=tool_output if isinstance(tool_output, dict) else {"result": str(tool_output)},
                    prompt_tokens=200,
                    completion_tokens=100
                )

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

            # 3. Finalize Successful Execution
            state.status = AgentStatus.COMPLETED
            duration_ms = int((time.time() - start_time) * 1000)
            await self.checkpointer.save_checkpoint(state)

            # 4. Save durable trace into SQLite
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

            return state

        except BudgetExceededException as e:
            state.status = AgentStatus.BUDGET_EXCEEDED
            state.context_data["error"] = str(e)
            await self.checkpointer.save_checkpoint(state)
            raise

        except asyncio.CancelledError:
            state.status = AgentStatus.SUSPENDED
            state.context_data["status_reason"] = "Task cancelled"
            await self.checkpointer.save_checkpoint(state)
            raise

        except Exception as e:
            state.status = AgentStatus.FAILED
            state.context_data["error"] = str(e)
            await self.checkpointer.save_checkpoint(state)
            raise

        finally:
            self._active_tasks.pop(agent_id, None)

    async def resume_agent(self, agent_id: str, config: AgentConfig) -> AgentState:
        """
        Resumes an agent execution loop from its Redis Hash checkpoint (<2 sec recovery).
        """
        checkpoint = await self.checkpointer.load_checkpoint(agent_id)
        if checkpoint is None:
            raise ValueError(f"No state checkpoint found for agent '{agent_id}' to resume.")

        logger.info(f"Resuming agent '{agent_id}' from step {checkpoint.current_step_index}")
        return await self.execute_agent_loop(config)
