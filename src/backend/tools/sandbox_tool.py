from typing import Dict, Any
from src.backend.tools.base import BaseTool
from src.backend.tools import execute_sandboxed_code


class CPPSandboxTool(BaseTool):
    """
    Agent tool interfacing the native C++ sandboxed code runner module via pybind11.
    """

    def __init__(
        self,
        default_timeout_ms: int = 5000,
        default_max_retries: int = 2
    ):
        super().__init__(
            name="cpp_sandbox",
            description="Executes native command/code under C++ process isolation and resource limits",
            default_timeout_ms=default_timeout_ms,
            default_max_retries=default_max_retries
        )

    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes sandboxed native command.
        Expected params: {"command": str, "timeout_ms": int, "memory_limit_mb": int}
        """
        command = params.get("command") or params.get("code")
        if not command:
            raise ValueError("Parameter 'command' or 'code' is required for cpp_sandbox tool")

        timeout_ms = params.get("timeout_ms", self.default_timeout_ms)
        memory_limit_mb = params.get("memory_limit_mb", 256)

        if execute_sandboxed_code is None:
            raise RuntimeError("Native C++ pybind11 module 'native_sandbox_cpp' is not compiled or available.")

        # Invoke C++ native runner
        result_dict = execute_sandboxed_code(
            command=command,
            timeout_ms=timeout_ms,
            memory_limit_mb=memory_limit_mb
        )

        if not result_dict.get("success", False):
            if result_dict.get("timed_out", False):
                raise TimeoutError(f"C++ Sandbox command timed out: {result_dict.get('error_message')}")
            else:
                raise RuntimeError(f"C++ Sandbox execution failed: {result_dict.get('error_message')}")

        return result_dict
