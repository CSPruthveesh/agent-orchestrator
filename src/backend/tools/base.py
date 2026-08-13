import time
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.backend.engine.models import ToolCallResult

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Abstract Base Class for agent tools enforcing exponential backoff retries
    and per-tool execution deadline policies.
    """

    def __init__(
        self,
        name: str,
        description: str,
        default_timeout_ms: int = 5000,
        default_max_retries: int = 3,
        backoff_base: float = 2.0
    ):
        self.name = name
        self.description = description
        self.default_timeout_ms = default_timeout_ms
        self.default_max_retries = default_max_retries
        self.backoff_base = backoff_base

    @abstractmethod
    async def run(self, params: Dict[str, Any]) -> Any:
        """
        Abstract method implemented by specific tool classes (e.g. HTTP fetch, C++ Sandbox).
        """
        pass

    async def execute_with_retry_and_timeout(
        self,
        params: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> ToolCallResult:
        """
        Executes the tool with strict timeout wrapping (`asyncio.wait_for`)
        and exponential backoff retry policy on failure.
        """
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        effective_max_retries = max_retries if max_retries is not None else self.default_max_retries

        start_time = time.time()
        attempt = 0
        last_error: Optional[str] = None

        while attempt <= effective_max_retries:
            attempt += 1
            try:
                # Enforce per-attempt hard execution timeout
                timeout_seconds = effective_timeout_ms / 1000.0
                output = await asyncio.wait_for(self.run(params), timeout=timeout_seconds)

                duration_ms = int((time.time() - start_time) * 1000)
                return ToolCallResult(
                    tool_name=self.name,
                    status="SUCCESS",
                    output=output,
                    execution_time_ms=duration_ms
                )

            except asyncio.TimeoutError:
                last_error = f"Tool '{self.name}' timed out after {effective_timeout_ms}ms (Attempt {attempt}/{effective_max_retries + 1})"
                logger.warning(last_error)

            except Exception as e:
                last_error = f"Tool '{self.name}' failed with error: {str(e)} (Attempt {attempt}/{effective_max_retries + 1})"
                logger.warning(last_error)

            # Apply exponential backoff before retry if retries remain
            if attempt <= effective_max_retries:
                delay = (self.backoff_base ** (attempt - 1)) * 0.1
                await asyncio.sleep(delay)

        duration_ms = int((time.time() - start_time) * 1000)
        status = "TIMEOUT" if "timed out" in (last_error or "").lower() else "FAILED"
        return ToolCallResult(
            tool_name=self.name,
            status=status,
            output=None,
            execution_time_ms=duration_ms,
            error=last_error
        )
