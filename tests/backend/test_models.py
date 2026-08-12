from src.backend.engine.models import (
    AgentConfig,
    AgentState,
    AgentStatus,
    ExecutionStep,
    StepNodeType,
    ToolCallRequest,
    ToolCallResult
)


def test_agent_config_defaults():
    """
    Asserts default field initialization for AgentConfig model.
    """
    config = AgentConfig(goal="Autonomous web research")
    assert config.goal == "Autonomous web research"
    assert config.model == "gemini-2.5-flash"
    assert config.max_budget_usd == 1.00
    assert "cpp_sandbox" in config.available_tools
    assert "http_tool" in config.available_tools
    assert config.max_workers == 3


def test_tool_call_models():
    """
    Asserts validation and serialization for ToolCallRequest and ToolCallResult.
    """
    request = ToolCallRequest(
        tool_name="cpp_sandbox",
        params={"code": "int main() { return 0; }"},
        timeout_ms=2000
    )
    assert request.tool_name == "cpp_sandbox"
    assert request.timeout_ms == 2000

    result = ToolCallResult(
        tool_name="cpp_sandbox",
        status="SUCCESS",
        output="Process exited with code 0",
        execution_time_ms=18
    )
    assert result.status == "SUCCESS"
    assert result.execution_time_ms == 18


def test_agent_state_transitions():
    """
    Asserts step tracking, state updates, and token token accumulation in AgentState.
    """
    state = AgentState(agent_id="agent-001")
    assert state.status == AgentStatus.IDLE
    assert state.current_step_index == 0

    step = ExecutionStep(
        agent_id="agent-001",
        node_type=StepNodeType.LLM_REASONING,
        prompt_tokens=50,
        completion_tokens=25,
        step_cost_usd=0.001
    )
    state.history.append(step)
    state.current_step_index += 1
    state.accumulated_tokens += step.prompt_tokens + step.completion_tokens
    state.accumulated_cost_usd += step.step_cost_usd
    state.status = AgentStatus.RUNNING

    assert state.status == AgentStatus.RUNNING
    assert state.current_step_index == 1
    assert state.accumulated_tokens == 75
    assert state.accumulated_cost_usd == 0.001
    assert len(state.history) == 1
    assert state.history[0].node_type == StepNodeType.LLM_REASONING
