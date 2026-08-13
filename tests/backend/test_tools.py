import pytest
import asyncio
from typing import Dict, Any
from src.backend.tools.base import BaseTool
from src.backend.tools.http_tool import AsyncHTTPTool
from src.backend.tools.sandbox_tool import CPPSandboxTool


class MockFailingTool(BaseTool):
    def __init__(self, fail_count: int = 2):
        super().__init__(name="mock_failing", description="Mock tool that fails N times")
        self.fail_count = fail_count
        self.attempts_made = 0

    async def run(self, params: Dict[str, Any]) -> str:
        self.attempts_made += 1
        if self.attempts_made <= self.fail_count:
            raise RuntimeError(f"Simulated error attempt {self.attempts_made}")
        return "Success on attempt " + str(self.attempts_made)


class MockTimeoutTool(BaseTool):
    def __init__(self):
        super().__init__(name="mock_timeout", description="Mock tool that sleeps forever")

    async def run(self, params: Dict[str, Any]) -> str:
        await asyncio.sleep(10.0)
        return "Finished"


@pytest.mark.asyncio
async def test_tool_exponential_retry_recovery():
    """
    Asserts that tool retries up to max_retries and succeeds on subsequent attempt.
    """
    tool = MockFailingTool(fail_count=2)
    res = await tool.execute_with_retry_and_timeout(
        params={},
        timeout_ms=2000,
        max_retries=3
    )

    assert res.status == "SUCCESS"
    assert res.output == "Success on attempt 3"
    assert tool.attempts_made == 3


@pytest.mark.asyncio
async def test_tool_timeout_exhaustion():
    """
    Asserts that tool execution exceeding deadline returns TIMEOUT status after retries.
    """
    tool = MockTimeoutTool()
    res = await tool.execute_with_retry_and_timeout(
        params={},
        timeout_ms=100,  # 100ms timeout
        max_retries=1    # 1 retry attempt
    )

    assert res.status == "TIMEOUT"
    assert res.output is None
    assert "timed out" in res.error.lower()


@pytest.mark.asyncio
async def test_cpp_sandbox_tool_execution():
    """
    Asserts CPPSandboxTool execution via native pybind11 runner.
    """
    tool = CPPSandboxTool(default_timeout_ms=3000, default_max_retries=1)
    res = await tool.execute_with_retry_and_timeout(
        params={"command": "whoami"}
    )

    assert res.status == "SUCCESS"
    assert res.output["success"] is True
    assert len(res.output["stdout_output"]) > 0
